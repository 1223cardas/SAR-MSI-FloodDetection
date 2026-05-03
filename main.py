import argparse
import logging
import os
import sys
from pathlib import Path

import numpy as np
import rasterio
from dotenv import load_dotenv
from rasterio.warp import Resampling, reproject

from processors import S1Processor, S2Processor

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sar_msi")

load_dotenv()


def ensure_s1_tif(paths, gptExec):
    out_dir = Path(paths["out"])
    tifs = list(out_dir.glob("floodImage*.tif"))
    if tifs:
        return tifs[0]

    # If no tif exists, try to generate via the visualization workflow
    logger.info("No S1 flood TIF found, generating visualization via SNAP workflows...")
    from S1 import scriptS1

    scriptS1.calculateAndDisplayResults(gptExec, paths)
    tifs = list(out_dir.glob("floodImage*.tif"))
    if not tifs:
        raise FileNotFoundError("Failed to produce S1 flood TIF in S1/out/")
    return tifs[0]


def combine_masks(s1_path, s2_path, out_path, method="or"):
    with rasterio.open(s1_path) as s1src, rasterio.open(s2_path) as s2src:
        s1_mask = s1src.read(1).astype("uint8")

        dest = np.zeros((s1src.height, s1src.width), dtype="float32")
        reproject(
            source=s2src.read(1),
            destination=dest,
            src_transform=s2src.transform,
            src_crs=s2src.crs,
            dst_transform=s1src.transform,
            dst_crs=s1src.crs,
            resampling=Resampling.nearest,
        )

        s2_aligned = (dest > 0.5).astype("uint8")

        if method == "or":
            combined = ((s1_mask == 1) | (s2_aligned == 1)).astype("uint8")
        else:
            combined = ((s1_mask == 1) & (s2_aligned == 1)).astype("uint8")

        profile = s1src.profile.copy()
        profile.update(driver="GTiff", dtype="uint8", count=1, compress="lzw", nodata=0)

        with rasterio.open(out_path, "w", **profile) as dst:
            dst.write(combined, 1)

    logger.info("Combined mask written to: %s", os.path.abspath(out_path))


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
    p.add_argument("--combine", action="store_true", help="Combine S1 and S2 flood masks after processing")
    p.add_argument("--combine-method", choices=["or", "and"], default="or", help="Combine method for masks")
    p.add_argument("--combined-out", default="combined_flood.tif", help="Output path for combined mask")
    return p


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not (args.use_s1 or args.use_s2):
        logger.error("Choose at least one source: --use-s1 and/or --use-s2")
        parser.print_help()
        sys.exit(1)

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
                result = s1_processor.run(run_processing=args.run, view=args.view or args.combine)
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
                result = s2_processor.run(run_processing=args.run, view=args.view or args.combine)
                s2_tif = result.output_path
                if s2_tif is not None:
                    logger.info("S2 flood TIF: %s", s2_tif)
            except Exception:
                logger.exception("S2 processing error")
                sys.exit(4)

    if args.combine:
        if s1_tif is None or s2_tif is None:
            logger.error("Both S1 and S2 masks are required to combine. Aborting.")
            sys.exit(1)

        combine_masks(str(s1_tif), str(s2_tif), args.combined_out, method=args.combine_method)


if __name__ == "__main__":
    main()
