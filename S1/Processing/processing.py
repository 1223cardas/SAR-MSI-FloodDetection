from Acquisition.modules.search_log import updateLogEntry
from .modules.discovery import getEntry, getFloodDataFile
from .modules.pipeline import runProcessing, runStacking, runMaskCreation, convertFloodToTif
from .modules.product_utils import get_band_file
from .modules.raster_utils import computeFloodArea, displayResults
from .modules.paths import build_output_file, checkEntryInOutput
from .modules.pclasses import ProductData
from .modules.snap import getExecutable

from pathlib import Path
import rasterio

def processProducts(gptExec: list[str]) -> None:
    print("Starting product processing...")
    entry = getEntry()

    # TODO: Add check for final product existence to skip processing if already done
    output_naming, processed_at = checkEntryInOutput(entry)
    updateLogEntry(entry, {"processed_at": processed_at})

    # 1. Process SNAP products to cache
    cachedProducts = runProcessing(entry, gptExec)

    # 2. Run stacking workflow to prepare variables for flood mask creation
    dimStack_file = runStacking(cachedProducts, gptExec)

    # 3. Create flood mask product
    dimFlood_file = runMaskCreation(dimStack_file, output_naming, gptExec)

    # 4. Save flood as tif to fuse with S2 results
    convertFloodToTif(dimFlood_file, output_naming, gptExec)

    print("Product processing complete.\n")

    return


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


def main():
    processProducts(gptExec=getExecutable())
    calculateAndDisplayResults()


if __name__ == "__main__":
    main()