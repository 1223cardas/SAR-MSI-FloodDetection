from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent # Acquisition/ folder
OUTPUT_DIR = ROOT_DIR / "downloads"
AQUISTION_DIR = ROOT_DIR / "Acquisition"
LOG_PATH = AQUISTION_DIR / "search_log.csv"