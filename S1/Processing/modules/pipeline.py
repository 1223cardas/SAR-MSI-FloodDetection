from pathlib import Path

from .pclasses import Product
from .paths import build_cache_file, build_output_file
from .discovery import discoverProducts, discoverAOI, getProductFile
# from .product_utils import computeWorkflowVariables
from .raster_utils import convertFileToTif
from .pipeline_utils import setupExecution, checkSuffixForFile
from .utils import refactor_snap_product

from .product_utils import computeWorkflowVariables   # keep — but its contents change
from .masking import export_clean_tif                 # replaces convertFileToTif

def runProcessing(entry: dict, gptExec: list[str]) -> list[Product]:
    area_of_interest = discoverAOI(entry)
    products = discoverProducts(entry)

    result: list[Product] = []

    print("Processing products...")
    for product in products:
        print(f"|\tProcessing {product.name}")

        output_path = build_cache_file(f"{entry.get('place_query')}_{product.parseDate()}")
        
        dim_file, dimExists = checkSuffixForFile(output_path, ".dim")
        currProduct = Product(name=output_path.name, path=dim_file, date=product.date)
        
        if dimExists:
            print(f"|\t[INFO] Found cache for {product.name}, skipping processing.")
            result.append(currProduct)
            continue

        proc_fileNaming = str(output_path) + '_PROCESSING'
        args = {
            "product": str(getProductFile(product.path)),
            "polygonRegion": area_of_interest,
            "output": proc_fileNaming
        }

        executed = setupExecution("singleProductProcessing", args, gptExec)
        if not executed:
            print(f"|\t[ERROR] Skipping {product.name} due to subset failure.")
            continue

        _, procDimExists = checkSuffixForFile(Path(proc_fileNaming), ".dim")
        if not procDimExists:
            print(f"|\t[ERROR] SNAP output missing for {product.name}; skipping refactor.")
            continue

        refactor_snap_product(proc_fileNaming)
        result.append(currProduct)

    print("Finished processing products.")

    if len(result) < 2:
        raise RuntimeError(
            "At least two products must be processed successfully before stacking."
            "Check prior errors and re-run."
        )

    result.sort(key=lambda p: p.date) # Make sure the products are ordered by date
    return result




def runStacking(cached_products: list[Product], gptExec: list[str]) -> Path:
    print("Stacking products...")
    date = "_".join(p.parseDate() for p in cached_products)

    stack_path = build_cache_file("stack_" + date)

    stackDim_file, stackDimExists = checkSuffixForFile(stack_path, ".dim")
    if stackDimExists:
        print(f"|\tStack file already exists: {stack_path}, skipping stacking step.")
        return stackDim_file

    stack_fileNaming = str(stack_path) + "_PROCESSING"
    args = {
        "product1": str(cached_products[0].path),
        "product2": str(cached_products[1].path),
        "output": stack_fileNaming
    }

    executed = setupExecution("stackProducts", args, gptExec)

    if not executed:
        raise RuntimeError("Stacking failed — check SNAP output above.")

    refactor_snap_product(stack_fileNaming)
    return stackDim_file



def runMaskCreation(dimStack_file: Path, namingScheme: str, gptExec: list[str]) -> Path:
    print("Creating flood mask...")

    flood_path = build_output_file(namingScheme)

    floodDim_file, floodDimExists = checkSuffixForFile(flood_path, ".dim")
    if floodDimExists:
        print(f"|\tFlood product already exists: {flood_path}, skipping file creation step.")
        return floodDim_file

    stack_variables = computeWorkflowVariables(dimStack_file)

    flood_fileNaming = str(flood_path) + "_PROCESSING"
    args = {
        "product": str(dimStack_file),
        "output": flood_fileNaming
    }
    args.update(stack_variables)

    executed = setupExecution("createMask", args, gptExec)

    if not executed:
        raise RuntimeError("Flood mask creation failed — check SNAP output above.")

    refactor_snap_product(flood_fileNaming)

    return floodDim_file


def convertFloodToTif(flood_dim: Path, namingScheme: str) -> Path:
    tif_path = build_output_file(f"{namingScheme}.tif")

    print("Saving flood product to TIFF...")
    if tif_path.exists():
        print(f"|\tFlood TIFF already exists: {tif_path}, skipping conversion.")
        return tif_path
    
    export_clean_tif(flood_dim, tif_path)

    return tif_path
