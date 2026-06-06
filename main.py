import argparse
import logging
import sys
from pathlib import Path

from processors import S1Processor, S2Processor
from Combined.combine import fuse_flood_outputs

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sar_msi")


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
    s2.add_argument("--imagens", default="Imagens")
    s2.add_argument("--s2-out", default="ndwi_work")
    s2.add_argument("--threshold", type=float, default=None)

    # Pipeline de Fusão Isolada
    fusion = sub.add_parser("fusion", help="Sentinel-1 and Sentinel-2 Data Fusion pipeline")
    fusion.add_argument("--s1-tif", required=True, help="Path to Sentinel-1 flood binary water mask TIF")
    fusion.add_argument("--s2-tif", default="ndwi_work/flood.tif", help="Path to Sentinel-2 flood SCL-weighted TIF")
    fusion.add_argument("--out-tif", default="flood_fused_continuous.tif", help="Path for the final output TIF")

    # Pipeline Completo Automático (S1 + S2 + Fusão de uma vez com bypass inteligente)
    total = sub.add_parser("all", help="Run complete S1 + S2 + Fusion pipeline automatically")
    total.add_argument("--imagens", default="Imagens")
    total.add_argument("--s2-out", default="ndwi_work")
    total.add_argument("--threshold", type=float, default=None)
    total.add_argument("--out-tif", default="flood_fused_continuous.tif")

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
                logger.info("A iniciar a fusão de sensores isolada...")
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

            logger.info("A iniciar pipeline unificado automático (s1 + s2 + fusão)")

            # -----------------------------------------------------------------
            # Passo 1: Verificar/Processar Sentinel-1 (Radar)
            # -----------------------------------------------------------------
            logger.info("[passo 1/3] a verificar/processar dados Sentinel-1 (radar)...")
            try:
                root_dir = Path(__file__).resolve().parent
                s1_output_dir = root_dir / "S1" / "output"
                s1_path = None
                temp_found_path = None
                
                if s1_output_dir.exists():
                    tifs = list(s1_output_dir.glob("*_flood.tif"))
                    if tifs:
                        temp_found_path = max(tifs, key=lambda p: p.stat().st_mtime)
                        
                        print(f"\n[s1] detetado ficheiro existente: {temp_found_path.name}")
                        resposta = input("Desejas usar este resultado do Sentinel-1 e saltar o processamento? (y/n): ").strip().lower()
                        
                        if resposta.lower() in ["y", "yes", "s", "sim", ""]:
                            s1_path = temp_found_path
                            logger.info("[s1 skip] a usar o ficheiro existente por decisão do utilizador.")
                        else:
                            logger.info("[s1 force] ignorando o ficheiro antigo. O processamento vai ser forçado.")

                if not s1_path:
                    logger.info("[s1 process] a iniciar o S1Processor e o SNAP...")
                    
                    sys.stdout.flush()
                    sys.stderr.flush()
                    
                    try:
                        s1_processor = S1Processor()
                        s1_result = s1_processor.run(run_processing=True, view=False)
                        
                        if hasattr(s1_result, "output_path") and s1_result.output_path:
                            s1_path = s1_result.output_path
                        elif s1_result and Path(str(s1_result)).exists():
                            s1_path = s1_result
                    except Exception:
                        logger.warning("O processador interno do S1 falhou ou o menu de logs estava vazio.")
                    
                    # Salvaguarda: se o menu do log falhou mas temos o ficheiro no disco, 
                    # usamos o ficheiro antigo para não abortar os passos seguintes do pipeline!
                    if not s1_path and temp_found_path:
                        s1_path = temp_found_path
                        logger.info("[s1 salvaguarda] a recuperar o ficheiro existente para permitir a continuação do pipeline.")

                if not s1_path or not Path(s1_path).exists():
                    raise ValueError("Não foi possível determinar o ficheiro de output do S1 para a fusão.")
                
                logger.info("[s1 sucesso] caminho do radar fixado: %s", s1_path)
                
            except Exception:
                logger.exception("Erro crítico no processamento ou verificação do Sentinel-1")
                sys.exit(2)

            # -----------------------------------------------------------------
            # Passo 2: Verificar/Processar Sentinel-2 (Ótico)
            # -----------------------------------------------------------------
            print("\n" + "-"*60)
            logger.info("[passo 2/3] a verificar/processar dados Sentinel-2 (ótico + scl)...")
            try:
                s2_output_dir = Path(args.s2_out)
                s2_path = None
                temp_s2_found = None
                
                if s2_output_dir.exists():
                    s2_tifs = list(s2_output_dir.glob("*flood*.tif")) + list(s2_output_dir.glob("flood.tif"))
                    s2_tifs = list(set(s2_tifs))
                    
                    if s2_tifs:
                        temp_s2_found = max(s2_tifs, key=lambda p: p.stat().st_mtime)
                        
                        print(f"[s2] detetado ficheiro existente: {temp_s2_found.name}")
                        resposta = input("Desejas usar este resultado do Sentinel-2 e saltar o processamento? (y/n): ").strip().lower()
                        
                        if resposta in ["y", "yes", "s", "sim", ""]:
                            s2_path = temp_s2_found
                            logger.info("[s2 skip] a usar o ficheiro existente por decisão do utilizador.")
                        else:
                            logger.info("[s2 force] ignorando o ficheiro antigo. O processamento vai ser forçado.")

                if not s2_path:
                    logger.info("[s2 process] a iniciar o S2Processor...")
                    
                    sys.stdout.flush()
                    sys.stderr.flush()
                    
                    try:
                        s2_processor = S2Processor(
                            imagens_dir=args.imagens,
                            out_dir=args.s2_out,
                            preview=False,
                            threshold=args.threshold,
                        )
                        s2_result = s2_processor.run(run_processing=True, view=False)
                        
                        if hasattr(s2_result, "output_path") and s2_result.output_path:
                            s2_path = s2_result.output_path
                        elif s2_result and Path(str(s2_result)).exists():
                            s2_path = s2_result
                    except Exception:
                        logger.warning("O processador interno do S2 falhou.")
                        
                    if not s2_path and temp_s2_found:
                        s2_path = temp_s2_found
                        logger.info("[s2 salvaguarda] a recuperar o ficheiro existente para permitir a fusão.")

                if not s2_path or not Path(s2_path).exists():
                    raise FileNotFoundError(f"Não foi possível encontrar o flood.tif do S2 em '{args.s2_out}'.")
                
                logger.info("[s2 sucesso] caminho do ótico fixado: %s", s2_path)

            except Exception:
                logger.exception("Erro crítico no processamento ou verificação do Sentinel-2")
                sys.exit(4)

            # -----------------------------------------------------------------
            # Passo 3: Fusão Automática Contínua
            # -----------------------------------------------------------------
            print("\n" + "-"*60)
            logger.info("[passo 3/3] a executar fusão matricial contínua...")
            try:
                final_out = fuse_flood_outputs(
                    s1_flood_path=Path(s1_path),
                    s2_flood_path=Path(s2_path),
                    output_path=Path(args.out_tif)
                )
                logger.info("Pipeline concluído com sucesso!")
                logger.info("Ficheiro final pronto para o QGIS: %s", final_out)
            except Exception:
                logger.exception("Erro crítico na fusão final de dados")
                sys.exit(5)


if __name__ == "__main__":
    main()