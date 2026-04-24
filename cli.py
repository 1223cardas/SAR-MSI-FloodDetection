import argparse
import os

from discovery import auto_find_band_paths
from pipeline import run_pipeline
from preview import preview_outputs_only


def build_parser():
    parser = argparse.ArgumentParser(
        description="NDWI Flood Detection",
        epilog=(
            "Examples:\n"
            "  python test.py                # list B03/B08 10m pairs and choose by number\n"
            "  python test.py                # auto threshold based on water area (Otsu)\n"
            "  python test.py --threshold 0.02\n"
            "  python test.py --preview\n"
            "  python test.py --out ndwi_work --preview"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--b3b", help="B3 before")
    parser.add_argument("--b8b", help="B8 before")
    parser.add_argument("--b3a", help="B3 after")
    parser.add_argument("--b8a", help="B8 after")
    parser.add_argument(
        "--imagens",
        default="Imagens",
        help="Folder containing .SAFE products for B03/B08 10m automatic discovery",
    )
    parser.add_argument("--out", default="ndwi_work", help="Output folder")
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Open an interactive preview window after processing",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="NDWI threshold override. If omitted, threshold is auto-computed (Otsu).",
    )
    return parser


def resolve_band_paths(args, parser):
    manual_paths = [args.b3b, args.b8b, args.b3a, args.b8a]
    if all(manual_paths):
        return args.b3b, args.b8b, args.b3a, args.b8a
    if any(manual_paths):
        parser.error("Provide either all 4 band paths or none to use automatic search.")
    return auto_find_band_paths(args.imagens)


def maybe_preview_existing_outputs(out_folder, preview_flag, threshold):
    required_outputs = [
        os.path.join(out_folder, "ndwi_before.tif"),
        os.path.join(out_folder, "ndwi_after.tif"),
        os.path.join(out_folder, "water_before.tif"),
        os.path.join(out_folder, "water_after.tif"),
        os.path.join(out_folder, "flood.tif"),
    ]
    can_preview_existing = preview_flag and os.path.isdir(out_folder) and all(
        os.path.exists(path) for path in required_outputs
    )
    if can_preview_existing:
        preview_outputs_only(out_folder, threshold=threshold)
    return can_preview_existing


def main():
    parser = build_parser()
    args = parser.parse_args()

    if maybe_preview_existing_outputs(args.out, args.preview, args.threshold):
        return

    b3b, b8b, b3a, b8a = resolve_band_paths(args, parser)
    run_pipeline(
        b3b,
        b8b,
        b3a,
        b8a,
        args.out,
        preview=args.preview,
        threshold=args.threshold,
    )
