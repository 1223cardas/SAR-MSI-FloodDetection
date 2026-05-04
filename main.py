import argparse
import logging
import sys

from dotenv import load_dotenv

from processors import S1Processor, S2Processor

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sar_msi")

load_dotenv()


def build_parser():
    p = argparse.ArgumentParser(description="SAR-MSI Unified Flood Detection Tool")

    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", action="store_true", help="Run processing")
    mode.add_argument("--view", action="store_true", help="Preview results")

    sub = p.add_subparsers(dest="source", required=True)
    sub.add_parser("s1", help="Sentinel-1 pipeline")

    s2 = sub.add_parser("s2", help="Sentinel-2 pipeline")
    s2.add_argument("--imagens", default="Imagens")
    s2.add_argument("--s2-out", default="ndwi_work")
    s2.add_argument("--threshold", type=float, default=None)

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

if __name__ == "__main__":
    main()