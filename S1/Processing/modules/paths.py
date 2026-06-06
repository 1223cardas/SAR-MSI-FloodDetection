from datetime import datetime
from pathlib import Path
import glob
import os
import shutil

# define the paths variable to be used across modules
paths: dict[str, Path] = {}

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

    # Clean cache directory
    if paths["cache"].exists():
        for f in glob.glob(str(paths["cache"] / "*_PROCESSING.*")):
            try:
                if os.path.isfile(f):
                    os.remove(f)
                elif os.path.isdir(f):
                    shutil.rmtree(f)
            except Exception as e:
                print(f"|\tWarning: Could not delete {f}. Reason: {e}")

    for d in paths.values():
        if not d.exists():
            print(f"\n|\t{d} doesn't exist. Creating directory...")
            d.mkdir(parents=True, exist_ok=True)

    print("Done.")
    return paths


def build_file(dir_path: Path, base_name: str) -> Path:
    """Build a file path in the specified directory with the given base name."""
    path = dir_path / base_name
    files_in_dir = list(path.parent.glob(f"{base_name}*"))

    if not files_in_dir:
        return path

    return path


def build_cache_file(base_name: str) -> Path:
    return build_file(paths["cache"], base_name)


def build_output_file(base_name: str) -> Path:
    return build_file(paths["out"], base_name)


def checkEntryInOutput(entry: dict) -> tuple[str, str]:
    dt_str = format(datetime.now(), '%Y-%m-%d_%H-%M-%S')
    date = entry.get("processed_at", dt_str)
    entry_naming = f"{entry.get("place_query")}_{date}_flood"

    expected_tif = build_output_file(entry_naming + ".tif")
    expected_data = build_output_file(entry_naming + ".dim")
    expected_dim = build_output_file(entry_naming + ".dim")

    if all(p.exists() for p in [expected_tif, expected_data, expected_dim]):
        print(f"\nFinal product already exists for this entry at: {expected_tif}")
        print("Skipping processing for this entry.")
        exit(0)
        
    return entry_naming, date
