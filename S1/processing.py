from pathlib import Path

from S1.models import Product
from S1.paths import build_cache_file, build_output_file
from S1.discovery import getProductFile, getShapeFile, getWorkflow
from S1.snap import execute_command
from S1.product_utils import computeWorkflowVariables, refactor_snap_product
from S1.raster_utils import compute_water_elevation_p95, compute_otsu_threshold_vh_diff, compute_otsu_threshold_vv_diff


def runProcessing(snap_products: list[Product], gptExec: list[str]) -> list[Product]:
    region_of_interest = getShapeFile()
    result: list[Product] = []

    print("Processing products...")
    for product in snap_products:
        print(f"|\tProcessing {product.name}")

        output_path = build_cache_file(f"{Path(region_of_interest.name).stem}_{product.parseDate()}")
        dim_file = Path(str(output_path) + ".dim")
        product_output = Product(name=output_path.name, path=dim_file, date=product.date)

        if dim_file.exists():
            print(f"|\t|\t[INFO] Cached product found for {product.name}, skipping processing.")
            result.append(product_output)
            continue

        cmd = gptExec.copy()
        cmd.extend(
            [
                str(getWorkflow("singleProductProcessing")),
                f"-Pproduct={str(getProductFile(product.path))}",
                f"-PvectorFile={str(region_of_interest)}",
                f"-Poutput={Path(str(output_path) + '_PROCESSING')}",
            ]
        )

        execute_command(
            cmd,
            success_message=f"|\t|\tSuccessfully processed {product.name}.\n"
            f"|\t|\tOutput saved to {product_output.path}",
            error_message=f"|\t|\t[ERROR] processing {product.name}:",
        )

        refactor_snap_product(str(output_path) + "_PROCESSING")
        result.append(product_output)

    print("Finished processing products.")

    if len(result) < 2:
        raise RuntimeError(
            "At least two products must be processed successfully before stacking. "
            "Check prior errors and re-run."
        )

    return result


def runStacking(cachedProducts: list[Product], gptExec: list[str]) -> Path:
    date = "_".join(p.parseDate() for p in cachedProducts)
    result = build_cache_file("stack_" + date)
    dimStack_file = Path(str(result) + ".dim")

    print("Stacking products...")
    if dimStack_file.exists():
        print(f"|\tStack file already exists: {result}, skipping stacking step.")
        return dimStack_file

    cmd = gptExec.copy()
    cmd.extend(
        [
            str(getWorkflow("stackProducts")),
            f"-Pproduct1={str(cachedProducts[0].path)}",
            f"-Pproduct2={str(cachedProducts[1].path)}",
            f"-Poutput={result}",
        ]
    )

    execute_command(
        cmd,
        success_message=f"|\tSuccessfully stacked products.\nOutput saved to {result}",
        error_message="|\tError stacking products:",
    )

    return dimStack_file


def runMaskCreation(dimStack_file: Path, gptExec: list[str]) -> Path:
    date = dimStack_file.stem.replace("stack_", "")
    result = build_output_file("flood_" + date)
    dimFlood_file = Path(str(result) + ".dim")

    print("Creating flood mask...")
    if dimFlood_file.exists():
        print(f"|\tFlood product already exists: {result}, skipping file creation step.")
        return dimFlood_file
    
    elevFunc = compute_water_elevation_p95
    otsuVVFunc = compute_otsu_threshold_vv_diff
    otsuVHFunc = compute_otsu_threshold_vh_diff
    stack_variables = computeWorkflowVariables(dimStack_file, elevFunc, otsuVVFunc, otsuVHFunc)

    cmd = gptExec.copy()
    cmd.extend(
        [
            str(getWorkflow("createMask")),
            f"-Pproduct={str(dimStack_file)}",
            f"-PhasDataAtPixel={stack_variables['hasDataAtPixel']}",
            f"-Pelev_threshold={stack_variables['elev_threshold']}",
            f"-Pvh_diff={stack_variables['vh_diff']}",
            f"-Pvv_diff={stack_variables['vv_diff']}",
            f"-Potsu_vh_threshold={stack_variables['otsu_vh']}",
            f"-Potsu_vv_threshold={stack_variables['otsu_vv']}",
            f"-Poutput={result}",
        ]
    )

    execute_command(
        cmd,
        success_message=f"|\tSuccessfully computed flood product.\n|\tOutput saved to {result}",
        error_message="|\t[ERROR] computing flood product:",
    )

    return dimFlood_file


def convertFloodToTif(flood_dim: Path, gptExec: list[str]) -> Path:
    tif_path = build_output_file(f"{flood_dim.stem}.tif")

    print("Saving flood product to TIFF...")
    if tif_path.exists():
        print(f"|\tFlood TIFF already exists: {tif_path}, skipping conversion.")
        return tif_path

    cmd = gptExec.copy()
    cmd.extend(
        [
            str(getWorkflow("convertToTif")),
            f"-Pinput={str(flood_dim)}",
            f"-Poutput={str(tif_path)}",
        ]
    )

    execute_command(
        cmd,
        success_message=f"|\tSuccessfully converted flood product to TIFF.\nOutput saved to {tif_path}",
        error_message="|\tError converting flood product to TIFF:",
    )

    return tif_path
