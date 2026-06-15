from typing import Any
from pathlib import Path
from dataclasses import fields
import re

from .raster_utils import (
    compute_water_elevation_p95,
    compute_water_class_ndsi_mean,
    compute_tile_otsu_tif,
    compute_slope_mask_tif,
    export_ndsi_tif
)
from .utils import get_band_file
from .pclasses import StackBands
from .paths import paths


def getBandsFromStack(dimstack_file: Path) -> StackBands:
    with open(dimstack_file, "r", encoding="ISO-8859-1") as f:
        content = f.read()

    bands: list[str] = re.findall(r"<BAND_NAME>(.*?)</BAND_NAME>", content)

    stackbands = StackBands()
    for b in bands:
        b_lower = b.lower()
        for field in fields(StackBands):
            if field.name in b_lower:
                setattr(stackbands, field.name, b)
                break

    missing = [
        field.name
        for field in fields(StackBands)
        if getattr(stackbands, field.name) == ""
    ]

    if missing:
        raise ValueError(
            "Could not extract all variable names from stack product.\n"
            f"Missing: {', '.join(missing)}\n"
            "Check that the stack was created correctly and band names are present."
        )

    return stackbands


def compileExpressions(bands: StackBands) -> tuple[str, str, str]:
    vhNDSIexpr = f"({bands.vh_slv} - {bands.vh_mst}) / ({bands.vh_slv} + {bands.vh_mst})"
    vvNDSIexpr = f"({bands.vv_slv} - {bands.vv_mst}) / ({bands.vv_slv} + {bands.vv_mst})"

    hasDataAtPixel = (
        f"( ({bands.vh_slv} > 0 AND {bands.vh_mst} > 0)"
        f" AND ({bands.vv_slv} > 0 AND {bands.vv_mst} > 0) )"
    )

    return vhNDSIexpr, vvNDSIexpr, hasDataAtPixel



def ensureNDSITIFexists(data_folder: Path, bands: StackBands) -> tuple[Path, Path]:
    vhNDSI_tif = paths["cache"] / "vh_ndsi.tif"
    vvNDSI_tif = paths["cache"] / "vv_ndsi.tif"

    if not vhNDSI_tif.exists():
        print("|\tExporting VH NDSI TIF...")
        export_ndsi_tif(data_folder, [bands.vh_slv, bands.vh_mst], vhNDSI_tif)

    if not vvNDSI_tif.exists():
        print("|\tExporting VV NDSI TIF...")
        export_ndsi_tif(data_folder, [bands.vv_slv, bands.vv_mst], vvNDSI_tif)

    return vhNDSI_tif, vvNDSI_tif


def ensureOtsuThresholdExists(vhDiff_tif: Path, vvDiff_tif: Path, lc_img: Path) -> tuple[Path, Path]:
    vhOtsuThr_tif = paths["cache"] / "vhOtsuThr.tif"
    vvOtsuThr_tif = paths["cache"] / "vvOtsuThr.tif"

    vh_ceiling = compute_water_class_ndsi_mean(str(vhDiff_tif), str(lc_img))
    vv_ceiling = compute_water_class_ndsi_mean(str(vvDiff_tif), str(lc_img))

    if not vhOtsuThr_tif.exists():
        print("|\tComputing VH threshold surface...")
        compute_tile_otsu_tif(vhDiff_tif, str(vhOtsuThr_tif), max_threshold=vh_ceiling)

    if not vvOtsuThr_tif.exists():
        print("|\tComputing VV threshold surface...")
        compute_tile_otsu_tif(vvDiff_tif, str(vvOtsuThr_tif), max_threshold=vv_ceiling)

    return vhOtsuThr_tif, vvOtsuThr_tif



def computeWorkflowVariables(dimstack_file: Path) -> dict[str, Any]:
    bands = getBandsFromStack(dimstack_file)
    vhNDSI_expr, vvNDSI_expr, hasDataAtPixel = compileExpressions(bands)

    data_folder = dimstack_file.with_suffix(".data")

    elev_threshold_tif = compute_water_elevation_p95(data_folder, [bands.elevation, bands.land_cover])
    vhNDSI_tif, vvNDSI_tif = ensureNDSITIFexists(data_folder, bands)


    lc_img = get_band_file(data_folder, bands.land_cover)
    vhOtsuThr_tif, vvOtsuThr_tif = ensureOtsuThresholdExists(vhNDSI_tif, vvNDSI_tif, lc_img)

    slope_mask_tif = paths["cache"] / "slope_mask.tif"
    if not slope_mask_tif.exists():
        print("|\tComputing slope mask...")
        elev_img = get_band_file(data_folder, bands.elevation)
        compute_slope_mask_tif(elev_img, slope_mask_tif)

    return {
        "elev_threshold_tif": str(elev_threshold_tif),
        "vh_threshold_tif": str(vhOtsuThr_tif),
        "vv_threshold_tif": str(vvOtsuThr_tif),
        "slope_mask_tif": str(slope_mask_tif),
        "hasDataAtPixel": hasDataAtPixel,
        "vh_diff": vhNDSI_expr,
        "vv_diff": vvNDSI_expr
    }

