from Acquisition.modules.search_log import updateLogEntry
from .modules.pipeline import *
from .modules.pclasses import ProductData
from .modules.utils import get_band_file
from .modules.discovery import getEntry, getFloodDataFile
from .modules.raster_utils import computeFloodArea, displayResults
from .modules.paths import build_output_file, checkEntryInOutput, cleanupTIFSInCache

from typing import Any, Callable, Optional
from pathlib import Path
import rasterio

def processProducts(gptExec: list[str], entry: dict | None = None, progress_callback: Optional[Callable[[float, Optional[str]], Any]] = None) -> Path:
    print("Starting product processing...")
    if entry is None:
        entry = getEntry()

    progress = progress_callback or (lambda *_args, **_kwargs: None)

    output_naming, processed_at, existing_tif = checkEntryInOutput(entry)
    if existing_tif is not None:
        return existing_tif

    updateLogEntry(entry, {"processed_at": processed_at})

    # 1. Process SNAP products to cache
    progress(0.3, "Processing Products...")
    cachedProducts = runProcessing(entry, gptExec)

    # 2. Run stacking workflow to prepare variables for flood mask creation
    progress(0.5, "Stacking products...")
    dimStack_file = runStacking(cachedProducts, gptExec)

    # 3. Create flood mask product
    progress(0.7, "Creating flood mask...")
    dimFlood_file = runMaskCreation(dimStack_file, output_naming, gptExec)


    # 4. Save flood as tif to fuse with S2 results
    progress(0.8, "Saving mask to tif file...")
    tif_path = convertFloodToTif(dimFlood_file, output_naming)

    print("Product processing complete.\n")
    cleanupTIFSInCache()

    return tif_path


def calculateAndDisplayResults() -> Path:
    data_path = getFloodDataFile()

    # Find the Flood band .img file
    flood_img = get_band_file(data_path, "Flood")

    print(f"\nReading flood mask from: {flood_img}")
    with rasterio.open(flood_img) as src:
        data = ProductData(
            band=src.read(1, masked=True),
            transform=src.transform,
            crs=src.crs,
            height=src.height,
            width=src.width,
        )

    flood_count, px_area_m2, total_area_m2 = computeFloodArea(data)

    displayResults(data_path, flood_count, px_area_m2, total_area_m2)

    tif_path = build_output_file(f"{data_path.stem}.tif")
    if not tif_path.exists():
        print(f"Flood TIFF not found at: {tif_path}")
        return data_path

    print(f"\nReading flood GeoTIFF from: {tif_path}")
    with rasterio.open(tif_path) as src:
        print(f"TIFF size: {src.width} x {src.height}")

    return data_path


# def main():
#     processProducts(gptExec=getExecutable())
#     calculateAndDisplayResults()


# if __name__ == "__main__":
#     main()