from pathlib import Path
import rasterio
import sys

from .discovery import getFloodDimFile, getProducts
from .models import Product, ProductData
from .processing import convertFloodToTif, runMaskCreation, runProcessing, runStacking
from .product_utils import get_band_file
from .raster_utils import computeFloodArea, displayResults
from .paths import build_output_file


def processProducts(gptExec: list[str]) -> None:
    print("Starting product processing...")
    snap_products: list[Product] = getProducts()

    # 1. Process SNAP products to cache
    cachedProducts = runProcessing(snap_products, gptExec)

    # 2. Run stacking workflow to prepare variables for flood mask creation
    dimStack_file = runStacking(cachedProducts, gptExec)

    # 3. Create flood mask product
    dimFlood_file = runMaskCreation(dimStack_file, gptExec)

    # 4. Save flood as tif to fuse with S2 results
    convertFloodToTif(dimFlood_file, gptExec)

    print("Product processing complete.\n")

    return


def calculateAndDisplayResults() -> Path:
    dim_path = getFloodDimFile()

    # Find the Flood band .img file
    flood_img = get_band_file(dim_path, "Flood")

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

    displayResults(dim_path, flood_count, px_area_m2, total_area_m2)

    tif_path = build_output_file(f"{dim_path.stem}.tif")
    if not tif_path.exists():
        print(f"Flood TIFF not found at: {tif_path}")
        return dim_path

    print(f"\nReading flood GeoTIFF from: {tif_path}")
    with rasterio.open(tif_path) as src:
        print(f"TIFF size: {src.width} x {src.height}")

    return dim_path


def main():
    # Suppress stack traces for cleaner error messages
    sys.tracebacklimit = 0
