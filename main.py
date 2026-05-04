import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from processors import S1Processor, S2Processor

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sar_msi")

load_dotenv()


def build_parser():
    p = argparse.ArgumentParser(description="SAR-MSI Unified Flood Detection Tool")
    p.add_argument("--use-s1", action="store_true", help="Run Sentinel-1 pipeline")
    p.add_argument("--use-s2", action="store_true", help="Run Sentinel-2 pipeline")
    p.add_argument("--run", action="store_true", help="Execute processing (not only preview)")
    p.add_argument("--view", action="store_true", help="Generate or view result images")
    p.add_argument("--imagens", default="Imagens", help="S2 input folder for auto discovery")
    p.add_argument("--s2-out", default="ndwi_work", help="S2 workspace folder")
    p.add_argument("--preview", action="store_true", help="S2 preview mode")
    p.add_argument("--threshold", type=float, default=None, help="S2 threshold override")
    return p


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not (args.use_s1 or args.use_s2):
        logger.error("Choose at least one source: --use-s1 and/or --use-s2")
        parser.print_help()
        sys.exit(1)

    if not (args.run or args.view or args.preview):
        logger.warning("No action specified. Use one of: --run, --view, or --preview")
        logger.info("Example: python3 main.py --use-s2 --run --view")
        sys.exit(0)

    s1_tif = None
    s2_tif = None

    if args.use_s1:
        logger.info("Preparing Sentinel-1 processing...")
        try:
            s1_processor = S1Processor()
        except Exception:
            logger.exception("Failed to initialize Sentinel-1 processor. Ensure SNAP_DIRECTORY is set.")
            sys.exit(2)

        if args.run or args.view:
            try:
                result = s1_processor.run(run_processing=args.run, view=args.view)
                s1_tif = result.output_path
                if s1_tif is not None:
                    logger.info("S1 flood TIF: %s", s1_tif)
            except Exception:
                logger.exception("S1 processing error")
                sys.exit(3)

    if args.use_s2:
        logger.info("Preparing Sentinel-2 processing...")
        try:
            s2_processor = S2Processor(
                imagens_dir=args.imagens,
                out_dir=args.s2_out,
                preview=args.preview,
                threshold=args.threshold,
            )
        except Exception:
            logger.exception("S2 processor initialization error")
            sys.exit(1)

        if args.run or args.view:
            try:
                result = s2_processor.run(run_processing=args.run, view=args.view)
                s2_tif = result.output_path
                if s2_tif is not None:
                    logger.info("S2 flood TIF: %s", s2_tif)
            except Exception:
                logger.exception("S2 processing error")
                sys.exit(4)


if __name__ == "__main__":
    main()
