import argparse
import logging
import sys
from pathlib import Path

from processors import S1Processor, S2Processor
from processors import build_s2_output_path
from Combined.combine import fuse_flood_outputs
from Acquisition.acquireProducts import acquireEntryFromLogWithBoth
from common import PromptCancelledError

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sar_msi")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_latest_tif(directory: Path, pattern: str) -> Path | None:
    """Devolve o TIF mais recente num diretório, ou None se não existir."""
    if not directory.exists():
        return None
    tifs = list(directory.glob(pattern))
    return max(tifs, key=lambda p: p.stat().st_mtime) if tifs else None


def _ask_reuse(path: Path, label: str) -> bool:
    """Pergunta ao utilizador se quer reutilizar um ficheiro existente."""
    print(f"\n[{label}] detetado ficheiro existente: {path.name}")
    answer = input(f"Desejas usar este resultado do {label} e saltar o processamento? (y/n): ").strip().lower()
    return answer in ("y", "yes", "s", "sim", "")


def resolve_s1(*, force: bool = False, entry: dict | None = None) -> Path | None:
    """
    Resolve o TIF de output do Sentinel-1.
    Se existir um ficheiro e force=False, pergunta ao utilizador se quer reutilizá-lo.
    Caso contrário, corre o S1Processor. Devolve o Path ou None em caso de falha.
    """
    root_dir = Path(__file__).resolve().parent
    s1_out_dir = root_dir / "S1" / "output"
    existing = _find_latest_tif(s1_out_dir, "*_flood.tif")

    if existing and not force and _ask_reuse(existing, "S1"):
        logger.info("[s1] a usar ficheiro existente.")
        return existing

    logger.info("[s1] a iniciar S1Processor e SNAP...")

    try:
        result = S1Processor().run(run_processing=True, view=False, entry=entry)
        path = _result_to_path(result)
        if path:
            return path
    except PromptCancelledError:
        raise
    except Exception:
        logger.exception("[s1] erro no processamento")

    if existing:
        logger.warning("[s1 salvaguarda] a usar ficheiro existente após falha do processador.")
        return existing

    logger.error("[s1] nenhum ficheiro de output encontrado.")
    return None


def resolve_s2(*, out_dir: str = "S2/output",
               threshold: float | None = None, force: bool = False, entry: dict | None = None) -> Path | None:
    """
    Resolve o TIF de output do Sentinel-2.
    Mesma lógica de reutilização/salvaguarda que o resolve_s1.
    """
    s2_out_dir = Path(out_dir)
    expected = build_s2_output_path(s2_out_dir, entry=entry)
    existing = expected if expected.exists() else None

    if existing is None and entry is None:
        existing = _find_latest_tif(s2_out_dir, "*flood*.tif")

    if existing and not force and _ask_reuse(existing, "S2"):
        logger.info("[s2] a usar ficheiro existente.")
        return existing

    logger.info("[s2] a iniciar S2Processor...")

    try:
        result = S2Processor(
            out_dir=out_dir,
            preview=False,
            threshold=threshold,
        ).run(run_processing=True, view=False, entry=entry)
        path = _result_to_path(result)
        if path:
            return path
    except PromptCancelledError:
        raise
    except Exception:
        logger.exception("[s2] erro no processamento")

    if existing:
        logger.warning("[s2 salvaguarda] a usar ficheiro existente após falha do processador.")
        return existing

    logger.error("[s2] nenhum ficheiro de output encontrado.")
    return None


def _result_to_path(result) -> Path | None:
    """Extrai um Path válido de um resultado de processador."""
    if result is None:
        return None
    if hasattr(result, "output_path") and result.output_path:
        return Path(result.output_path)
    candidate = Path(str(result))
    return candidate if candidate.exists() else None


def run_fusion(s1_path: Path, s2_path: Path, out_tif: str) -> Path | None:
    """Corre a fusão e devolve o Path do ficheiro final, ou None em caso de erro."""
    logger.info("[fusão] a fundir S1 + S2...")
    try:
        final = fuse_flood_outputs(
            s1_flood_path=s1_path,
            s2_flood_path=s2_path,
            output_path=Path(out_tif),
        )
        logger.info("[fusão] concluída — ficheiro final: %s", final)
        return final
    except PromptCancelledError:
        raise
    except Exception:
        logger.exception("[fusão] erro crítico")
        return None



def build_parser():
    p = argparse.ArgumentParser(description="SAR-MSI Unified Flood Detection Tool")

    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", action="store_true", help="Run processing / fusion")
    mode.add_argument("--view", action="store_true", help="Preview results")

    sub = p.add_subparsers(dest="source", required=True)
    
    # Pipeline Sentinel-1
    sub.add_parser("s1", help="Sentinel-1 pipeline")

    # Pipeline Sentinel-2
    s2 = sub.add_parser("s2", help="Sentinel-2 pipeline")
    s2.add_argument("--s2-out", default="S2/output")
    s2.add_argument("--threshold", type=float, default=None)

    # Pipeline de Fusão Isolada
    fusion = sub.add_parser("fusion", help="Sentinel-1 and Sentinel-2 Data Fusion pipeline")
    fusion.add_argument("--s1-tif", default="S1/output/Kherson_2026-06-06_15-17-32_flood.tif", help="Path to Sentinel-1 flood binary water mask TIF")
    fusion.add_argument("--s2-tif", default="", help="Path to Sentinel-2 flood SCL-weighted TIF")
    fusion.add_argument("--out-tif", default="flood_fused_continuous.tif", help="Path for the final output TIF")

    # Pipeline Completo Automático (S1 + S2 + Fusão de uma vez com bypass inteligente)
    total = sub.add_parser("all", help="Run complete S1 + S2 + Fusion pipeline automatically")
    total.add_argument("--s2-out", default="S2/output")
    total.add_argument("--threshold", type=float, default=None)
    total.add_argument("--out-tif", default="flood_fused_continuous.tif")

    auto = sub.add_parser("auto", help="Run program with available data for the given request")
    auto.add_argument("--s2-out", default="S2/output")
    auto.add_argument("--threshold", type=float, default=None)
    auto.add_argument("--out-tif", default="flood_fused_continuous.tif")

    return p


def main():
    args = build_parser().parse_args()

    try:
        match args.source:
            case "s1":
                logger.info("Preparing Sentinel-1 processing...")
                try:
                    result = S1Processor().run(run_processing=args.run, view=args.view)
                    if path := _result_to_path(result):
                        logger.info("S1 flood TIF: %s", path)
                except PromptCancelledError:
                    raise
                except Exception:
                    logger.exception("Erro S1")
                    sys.exit(3)

            case "s2":
                logger.info("A preparar Sentinel-2...")
                try:
                    result = S2Processor(
                        out_dir=args.s2_out,
                        preview=args.view,
                        threshold=args.threshold,
                    ).run(run_processing=args.run, view=args.view)
                    if path := _result_to_path(result):
                        logger.info("S2 flood TIF: %s", path)
                except PromptCancelledError:
                    raise
                except Exception:
                    logger.exception("Erro S2")
                    sys.exit(4) 


            case "fusion":
                if args.view:
                    logger.warning("Preview não implementado para a fusão.")
                    return
                if args.run:
                    s2_candidate = Path(args.s2_tif) if args.s2_tif else _find_latest_tif(Path("S2/output"), "*_flood.tif")
                    if s2_candidate is None:
                        logger.error("Nenhum output do S2 encontrado para a fusão.")
                        sys.exit(5)
                    if not run_fusion(Path(args.s1_tif), s2_candidate, args.out_tif):
                        sys.exit(5)

            case "auto":
                entries = acquireEntryFromLogWithBoth()
                if entries is None:
                    logger.error("No entries availible.")
                    sys.exit(1)
                
                s1_entry, s2_entry = entries 
                hasS1 = len(s1_entry.productFromIds()) == 2
                hasS2 = len(s2_entry.productFromIds()) == 2

                logger.info("Dados disponíveis — S1: %s | S2: %s", hasS1, hasS2)

                if not hasS1 and not hasS2:
                    logger.error("Nenhum dado disponível.")
                    sys.exit(1)

                s1_path = resolve_s1(force=True, entry=s1_entry.to_dict()) if hasS1 else None
                s2_path = resolve_s2(  
                    out_dir=args.s2_out,
                    threshold=args.threshold,
                    force=True,
                    entry=s2_entry.to_dict()
                ) if hasS2 else None

                if s1_path and s2_path:
                    if not run_fusion(s1_path, s2_path, args.out_tif):
                        sys.exit(5)
                elif s1_path:
                    logger.info("[auto] apenas S1 disponível — resultado: %s", s1_path)
                elif s2_path:
                    logger.info("[auto] apenas S2 disponível — resultado: %s", s2_path)
                else:
                    logger.error("[auto] nenhum ficheiro produzido apesar dos dados reportados.")
                    sys.exit(3)
    except PromptCancelledError:
        logger.info("Execução cancelada pelo utilizador.")

if __name__ == "__main__":
    import time
    start_time = time.time()
    main()
    print("--- %s seconds ---" % (time.time() - start_time))