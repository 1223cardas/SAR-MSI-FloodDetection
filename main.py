import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from processors import S1Processor, S2Processor
from Combined.combine import fuse_flood_outputs

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sar_msi")

load_dotenv()


def build_parser():
    p = argparse.ArgumentParser(description="SAR-MSI Unified Flood Detection Tool")

    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", action="store_true", help="Run processing / fusion")
    mode.add_argument("--view", action="store_true", help="Preview results")

    sub = p.add_subparsers(dest="source", required=True)
    
    # 1. Pipeline Sentinel-1
    sub.add_parser("s1", help="Sentinel-1 pipeline")

    # 2. Pipeline Sentinel-2
    s2 = sub.add_parser("s2", help="Sentinel-2 pipeline")
    s2.add_argument("--imagens", default="Imagens")
    s2.add_argument("--s2-out", default="ndwi_work")
    s2.add_argument("--threshold", type=float, default=None)

    # 3. Pipeline de Fusão Isolada
    fusion = sub.add_parser("fusion", help="Sentinel-1 and Sentinel-2 Data Fusion pipeline")
    fusion.add_argument("--s1-tif", required=True, help="Path to Sentinel-1 flood binary water mask TIF")
    fusion.add_argument("--s2-tif", default="ndwi_work/flood.tif", help="Path to Sentinel-2 flood SCL-weighted TIF")
    fusion.add_argument("--out-tif", default="flood_fused_continuous.tif", help="Path for the final output TIF")

    # 4. NOVO: Pipeline Completo Automático (S1 + S2 + Fusão tudo de uma vez!)
    total = sub.add_parser("all", help="Run complete S1 + S2 + Fusion pipeline automatically")
    total.add_argument("--imagens", default="Imagens", help="Sentinel-2 images directory")
    total.add_argument("--s2-out", default="ndwi_work", help="Sentinel-2 output directory")
    total.add_argument("--threshold", type=float, default=None, help="Manual threshold for S2 NDWI")
    total.add_argument("--out-tif", default="flood_fused_continuous.tif", help="Path for the final output TIF")

    return p


def main():
    args = build_parser().parse_args()

    match args.source:
        case "s1":
            logger.info("Preparing Sentinel-1 processing...")
            try:
                s1_processor = S1Processor()
            except Exception:
                logger.exception("Failed to initialize S1 processor. Is SNAP_DIRECTORY set?")
                sys.exit(2)
            try:
                result = s1_processor.run(run_processing=args.run, view=args.view)
                if result.output_path:
                    logger.info("S1 flood TIF: %s", result.output_path)
            except Exception:
                logger.exception("S1 processing error")
                sys.exit(3)

        case "s2":
            logger.info("Preparing Sentinel-2 processing...")
            try:
                s2_processor = S2Processor(
                    imagens_dir=args.imagens,
                    out_dir=args.s2_out,
                    preview=args.view,
                    threshold=args.threshold,
                )
            except Exception:
                logger.exception("S2 processor initialization error")
                sys.exit(1)
            try:
                result = s2_processor.run(run_processing=args.run, view=args.view)
                if result.output_path:
                    logger.info("S2 flood TIF: %s", result.output_path)
            except Exception:
                logger.exception("S2 processing error")
                sys.exit(4)

        case "fusion":
            if args.view:
                logger.warning("Preview não implementado para a fusão.")
            if args.run:
                logger.info("A iniciar a Fusão de Sensores Isolada...")
                try:
                    out_path = fuse_flood_outputs(
                        s1_flood_path=Path(args.s1_tif),
                        s2_flood_path=Path(args.s2_tif),
                        output_path=Path(args.out_tif)
                    )
                    logger.info("Fusão concluída! Ficheiro final: %s", out_path)
                except Exception:
                    logger.exception("Erro na fusão de dados")
                    sys.exit(5)

        case "all":
            if not args.run:
                logger.error("Para correr o pipeline completo precisas de usar a flag --run")
                sys.exit(6)

            logger.info("A iniciar a pipeline (S1 + S2 + FUSÃO)")

            # Passo 1: Executar Sentinel-1
            logger.info("[PASSO 1/3] A processar dados Sentinel-1 (Radar)...")
            try:
                s1_processor = S1Processor()
                s1_result = s1_processor.run(run_processing=True, view=False)
                s1_path = s1_result.output_path
                if not s1_path:
                    raise ValueError("O S1Processor não retornou um caminho de output válido.")
                logger.info("[S1 SUCESSO] Máscara S1 gerada em: %s", s1_path)
            except Exception:
                logger.exception("Erro crítico no processamento do Sentinel-1")
                sys.exit(2)

            # Passo 2: Executar Sentinel-2
            logger.info("[PASSO 2/3] A processar dados Sentinel-2 (Ótico + SCL)...")
            try:
                s2_processor = S2Processor(
                    imagens_dir=args.imagens,
                    out_dir=args.s2_out,
                    preview=False,
                    threshold=args.threshold,
                )
                s2_result = s2_processor.run(run_processing=True, view=False)
                s2_path = s2_result.output_path
                if not s2_path:
                    raise ValueError("O S2Processor não retornou um caminho de output válido.")
                logger.info("[S2 SUCESSO] Mapa de pesos S2 gerado em: %s", s2_path)
            except Exception:
                logger.exception("Erro crítico no processamento do Sentinel-2")
                sys.exit(1)

            # Passo 3: Fusão Automática de Ambos os Resultados
            logger.info("[PASSO 3/3] A executar fusão matricial contínua...")
            try:
                final_out = fuse_flood_outputs(
                    s1_flood_path=Path(s1_path),
                    s2_flood_path=Path(s2_path),
                    output_path=Path(args.out_tif)
                )
                logger.info("Pipeline concluído!")
                logger.info("Ficheiro final pronto para o QGIS: %s", final_out)
            except Exception:
                logger.exception("Erro crítico na fusão final de dados")
                sys.exit(5)


if __name__ == "__main__":
    main()