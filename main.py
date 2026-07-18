import argparse
import logging
import sys
from pathlib import Path

from Acquisition.acquireProducts import acquireEntryFromLogWithBoth
from processorsImpl import S1Processor, S2Processor
from Combined.combine import fuse_flood_outputs
from common import PromptCancelledError

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sar_msi")


def _resolve_processor(processor_instance, run_processing: bool, view: bool, entry: dict | None = None) -> Path | None:
    """Executes a processor workflow and extracts the output_path safely."""
    result = processor_instance.run(run_processing, view, entry)
    if result and hasattr(result, "output_path") and result.output_path:
        return Path(result.output_path)
    return None


def _find_latest_tif(directory: Path, pattern: str = "*_flood.tif") -> Path | None:
    """Locates the most recently modified TIF file matching the pattern inside a directory."""
    if not directory.exists():
        return None
    files = list(directory.glob(pattern))
    return max(files, key=lambda f: f.stat().st_mtime) if files else None


def run_s1_pipeline(run: bool, view: bool, entry: dict | None = None) -> Path | None:
    logger.info("[S1] Starting Sentinel-1 pipeline...")
    path = _resolve_processor(S1Processor(), run_processing=run, view=view, entry=entry)
    if path:
        logger.info("[S1] Flood TIF generated: %s", path)
    return path


def run_s2_pipeline(run: bool, view: bool, threshold: float | None = None, entry: dict | None = None) -> Path | None:
    logger.info("[S2] Starting Sentinel-2 pipeline...")
    path = _resolve_processor(S2Processor(threshold=threshold), run_processing=run, view=view, entry=entry)
    if path:
        logger.info("[S2] Flood TIF generated: %s", path)
    return path


def run_fusion_pipeline(s1_path: Path, s2_path: Path, out_tif: str) -> Path | None:
    logger.info("[Fusion] Fusing S1 and S2 results...")
    logger.info("[Fusion] Target S1 TIF: %s", s1_path)
    logger.info("[Fusion] Target S2 TIF: %s", s2_path)
    
    final = fuse_flood_outputs(
        s1_flood_path=s1_path,
        s2_flood_path=s2_path,
        output_path=Path(out_tif),
    )
    logger.info("[Fusion] Done! Final output map: %s", final)
    return final


def handle_fusion_mode(args):
    """Resolves input paths via arguments or fallback discovery, then runs fusion."""
    if args.view:
        logger.warning("Preview mode not implemented for the fusion sub-task.")
        return

    # S1 Target Resolution (Explicit argument -> Fallback to default directory)
    s1_candidate = Path(args.s1_tif) if args.s1_tif else _find_latest_tif(Path("S1/output"))
    if not s1_candidate or not s1_candidate.exists():
        logger.error("[Fusion] Error: No valid Sentinel-1 flood TIF specified or found in 'S1/output'.")
        sys.exit(5)

    # S2 Target Resolution (Explicit argument -> Fallback to default directory)
    s2_candidate = Path(args.s2_tif) if args.s2_tif else _find_latest_tif(Path("S2/output"))
    if not s2_candidate or not s2_candidate.exists():
        logger.error("[Fusion] Error: No valid Sentinel-2 flood TIF specified or found in 'S2/output'.")
        sys.exit(5)

    if not run_fusion_pipeline(s1_candidate, s2_candidate, args.out_tif):
        sys.exit(5)


def handle_automated_pipeline(args):
    """Fully automated execution pipeline branching off acquired entry pairs."""
    entries = acquireEntryFromLogWithBoth()
    if not entries:
        logger.error("[Auto] No data entries available in log.")
        sys.exit(1)
        
    s1_entry, s2_entry = entries 
    has_s1 = len(s1_entry.productFromIds()) == 2
    has_s2 = len(s2_entry.productFromIds()) == 2

    logger.info("[Auto] Available data pairs — S1: %s | S2: %s", has_s1, has_s2)

    if not has_s1 and not has_s2:
        logger.error("[Auto] Neither S1 nor S2 data pairs are available for processing.")
        sys.exit(1)

    s1_path = run_s1_pipeline(run=True, view=False, entry=s1_entry.to_dict()) if has_s1 else None
    s2_path = run_s2_pipeline(run=True, view=False, threshold=args.threshold, entry=s2_entry.to_dict()) if has_s2 else None

    if s1_path and s2_path:
        if not run_fusion_pipeline(s1_path, s2_path, args.out_tif):
            sys.exit(5)
    elif s1_path:
        logger.info("[Auto] Only Sentinel-1 processed — Output: %s", s1_path)
    elif s2_path:
        logger.info("[Auto] Only Sentinel-2 processed — Output: %s", s2_path)
    else:
        logger.error("[Auto] Target data was reported available, but no flood files were successfully produced.")
        sys.exit(3)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="SAR-MSI Unified Flood Detection Tool")

    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", action="store_true", help="Run processing / fusion")
    mode.add_argument("--view", action="store_true", help="Preview results")

    sub = p.add_subparsers(dest="source", required=True)
	
    # Sentinel-1 Pipeline
    sub.add_parser("s1", help="Sentinel-1 pipeline")

    # Sentinel-2 Pipeline
    s2 = sub.add_parser("s2", help="Sentinel-2 pipeline")
    s2.add_argument("--threshold", type=float, default=None)

    # Fusion Pipeline
    fusion = sub.add_parser("fusion", help="Sentinel-1 and Sentinel-2 Fusion pipeline")
    fusion.add_argument("--s1-tif", default=None, help="Path to Sentinel-1 flood TIF (Optional, auto-discovers if omitted)")
    fusion.add_argument("--s2-tif", default=None, help="Path to Sentinel-2 flood TIF (Optional, auto-discovers if omitted)")
    fusion.add_argument("--out-tif", default="flood_fused_continuous.tif", help="Path for the final output TIF")

    # Automated Pipeline
    auto = sub.add_parser("auto", help="Run program automatically with available data for the given request")
    auto.add_argument("--threshold", type=float, default=None)

    return p


def main():
    args = build_parser().parse_args()

    try:
        match args.source:
            case "s1":
                if not run_s1_pipeline(run=args.run, view=args.view):
                    sys.exit(3)

            case "s2":
                if not run_s2_pipeline(run=args.run, view=args.view, threshold=args.threshold):
                    sys.exit(4)

            case "fusion":
                handle_fusion_mode(args)

            case "auto":
                handle_automated_pipeline(args)

    except PromptCancelledError:
        logger.info("Execution prompt safely cancelled by user.")
    except Exception as e:
        logger.critical("Fatal runtime exception on %s pipeline: %s", args.source.upper(), e, exc_info=True)
        sys.exit(99)


if __name__ == "__main__":
    import time
    start_time = time.time()
    main()
    print(f"--- {time.time() - start_time:.4f} seconds ---")