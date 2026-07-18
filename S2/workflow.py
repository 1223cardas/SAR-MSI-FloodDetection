from pathlib import Path
from typing import Any, Callable, Optional

from Acquisition.modules.search_log import updateLogEntry

from .discovery import build_output_file, checkEntryInOutput, discover_all_band_pairs, getEntry
from .pipeline import run_pipeline


def processProducts(
	entry: dict | None = None,
	threshold: float | None = None,
	progress_callback: Optional[Callable[[float, Optional[str]], Any]] = None,
) -> Path:
	print(f"[S2] Processing products...")
	if entry is None:
		entry = getEntry()

	progress = progress_callback or (lambda *_: None)

	output_naming, date, existing_tif = checkEntryInOutput(entry)
	if existing_tif is not None:
		print(f"[INFO] TIF file already exists for {entry.get('place_name')}")
		return existing_tif

	if entry.get("processed_at") != date:
		updateLogEntry(entry, {"processed_at": ""})

	# 1. Discover before/after band pairs
	progress(20, "Discovering band pairs...")
	before, after = discover_all_band_pairs(entry)

	# 2. Run pixel-level processing pipeline
	progress(40, "Running S2 pipeline...")
	run_pipeline(
		before,
		after,
		output_name=output_naming + ".tif",
		preview=False,
		threshold=threshold,
		progress_callback=progress_callback,
	)

	tif_path = build_output_file(output_naming + ".tif")

	print("S2 product processing complete.\n")
	updateLogEntry(entry, {"processed_at": date})

	return tif_path
