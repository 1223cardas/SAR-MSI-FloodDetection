from .modules.paths import build_output_file, checkEntryInOutput, cleanupTIFSInCache
from Acquisition.modules.search_log import updateLogEntry
from .modules.masking import computeFloodArea
from .modules.pclasses import ProductData
from .modules.utils import displayResults
from .modules.discovery import getEntry
from .modules.pipeline import *

from typing import Any, Callable, Optional
from pathlib import Path
import numpy as np
import rasterio

def processProducts(gptExec: list[str], entry: dict | None = None, progress_callback: Optional[Callable[[float, Optional[str]], Any]] = None) -> Path:
	print(f"[S1] Processing products...")
	if entry is None:
		entry = getEntry()
	progress = progress_callback or (lambda *_: None)

	output_naming, date, existing_tif = checkEntryInOutput(entry)
	
	if existing_tif is not None:
		print(f"[INFO] TIF file already exists for {entry.get('place_name')} ")
		return existing_tif

	if entry.get("processed_at") != date:
		updateLogEntry(entry, {"processed_at": ""})

	# 1. Process SNAP products to cache
	progress(0.3, "Processing Products...")
	cachedProducts = runProcessing(entry, gptExec)

	# 2. Run stacking workflow to prepare variables for flood mask creation
	progress(0.5, "Stacking products...")
	dimStack_file = runStacking(entry, cachedProducts, gptExec)

	# 3. Create flood mask product
	progress(0.7, "Creating flood mask...")
	dimFlood_file = runMaskCreation(dimStack_file, output_naming, gptExec)

	# 4. Save flood as tif to fuse with S2 results
	progress(0.8, "Saving mask to tif file...")
	tif_path = convertFloodToTif(dimFlood_file, output_naming)

	print("Product processing complete.\n")
	cleanupTIFSInCache()

	updateLogEntry(entry, {"processed_at": date})

	return tif_path


def calculateAndDisplayResults() -> Path:
	entry = getEntry()
	entry_naming, _, _ = checkEntryInOutput(entry)

	tif_path = build_output_file(entry_naming + ".tif")
	if not tif_path.exists():
		print(f"No file found for path: {tif_path}")
		return tif_path

	with rasterio.open(tif_path) as src:
		print(f"TIFF size: {src.width} x {src.height} | CRS: {src.crs}")
		
		raw_band = src.read(1)
		flood_mask = raw_band > 0
		
		clean_band = np.ma.masked_where(~flood_mask, np.ones(raw_band.shape, dtype=np.float32))
		
		data = ProductData(
			band=clean_band,
			transform=src.transform,
			crs=src.crs,
			height=src.height,
			width=src.width,
		)

	flood_count, px_area_m2, total_area_m2 = computeFloodArea(data)

	displayResults(flood_count, px_area_m2, total_area_m2)

	return tif_path