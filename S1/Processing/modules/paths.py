from pathlib import Path
import glob
import os
import shutil

from common.shared_paths import checkEntryInOutput as _shared_checkEntryInOutput

# define the paths variable to be used across modules
paths: dict[str, Path] = {}


def _ensureDirsExist():
    for d in paths.values():
        if not d.exists():
            print(f"\n|\t{d} doesn't exist. Creating directory...")
            d.mkdir(parents=True, exist_ok=True)


def _cleanupProcessingInCache():
    if paths["cache"].exists():
        for f in glob.glob(str(paths["cache"] / "*_PROCESSING.*")):
            try:
                if os.path.isfile(f):
                    os.remove(f)
                elif os.path.isdir(f):
                    shutil.rmtree(f)
            except Exception as e:
                print(f"|\tWarning: Could not delete {f}. Reason: {e}")


def cleanupTIFSInCache():
    if paths["cache"].exists():
        for f in glob.glob(str(paths["cache"] / "*.tif")):
            os.remove(f)


def check_directories() -> dict[str, Path]:
    """Check and create necessary directories, and return a dictionary of the paths."""
    print("Checking directories...", end=" ")
    
    project_root = os.getcwd()
    s1_root = Path(project_root) / "S1"
    s1_processing_path = s1_root / "Processing" 

    out_dir = s1_root / "output"
    workflow_dir = s1_processing_path / "workflows"
    cache_dir = s1_processing_path / "processing_cache"

    global paths
    paths.update(
        {
            "out": out_dir,
            "cache": cache_dir,
            "workflows": workflow_dir
        }
    )

    _cleanupProcessingInCache()
    cleanupTIFSInCache()
    _ensureDirsExist()

    print("Done.")
    return paths


def _build_file(dir_path: Path, base_name: str) -> Path:
    """Build a file path in the specified directory with the given base name."""
    path = dir_path / base_name

    return path


def build_cache_file(base_name: str) -> Path:
    return _build_file(paths["cache"], base_name)


def build_output_file(base_name: str) -> Path:
    return _build_file(paths["out"], base_name)


def checkEntryInOutput(entry: dict) -> tuple[str, str, Path | None]:
    return _shared_checkEntryInOutput(entry, build_output_func=build_output_file)
