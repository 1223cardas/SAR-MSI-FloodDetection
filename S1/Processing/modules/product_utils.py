from pathlib import Path
from dataclasses import fields
from typing import Any
import re

from .masking import (
    compute_scene_offsets,
    compute_elevation_ceiling,
    compute_slope_mask,
    build_snap_expressions,
    compute_adaptive_thresholds
)
from .pclasses import StackBands
from .paths import paths


def getBandsFromStack(dimstack_file: Path) -> StackBands:
    """Parse band names from the .dim XML. Unchanged."""
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
    missing = [f.name for f in fields(StackBands) if getattr(stackbands, f.name) == ""]
    if missing:
        raise ValueError(
            f"Could not extract all band names from stack.\nMissing: {', '.join(missing)}"
        )
    return stackbands


def computeWorkflowVariables(dimstack_file: Path) -> dict[str, Any]:
    """
    Compute all variables needed by createMask.xml.

    Returns a dict whose keys match the ${...} parameters in the XML:
      - elev_ceiling_tif  — spatially adaptive elevation ceiling (GeoTIFF path)
      - slope_mask_tif    — binary slope mask (GeoTIFF path)
      - has_data          — SNAP BandMaths data-validity guard expression
      - vh_norm           — SNAP BandMaths normalized VH log-ratio expression
      - vv_norm           — SNAP BandMaths normalized VV log-ratio expression
    """
    bands = getBandsFromStack(dimstack_file)
    data_folder = dimstack_file.with_suffix(".data")

    # 1. Scene normalization offsets from permanent water pixels
    offset_vh, offset_vv = compute_scene_offsets(
        data_folder,
        vh_slv_name=bands.vh_slv,
        vh_mst_name=bands.vh_mst,
        vv_slv_name=bands.vv_slv,
        vv_mst_name=bands.vv_mst,
        lc_name=bands.land_cover,
    )

    # 2. Elevation ceiling surface
    elev_ceiling_tif = compute_elevation_ceiling(
        data_folder,
        elev_name=bands.elevation,
        lc_name=bands.land_cover,
        out_tif=paths["cache"] / "elev_ceiling.tif",
    )

    # 3. Slope mask
    slope_mask_tif = compute_slope_mask(
        data_folder,
        elev_name=bands.elevation,
        out_tif=paths["cache"] / "slope_mask.tif",
    )

    # After compute_scene_offsets:
    thresholds = compute_adaptive_thresholds(
        data_folder,
        vh_slv_name=bands.vh_slv, vh_mst_name=bands.vh_mst,
        vv_slv_name=bands.vv_slv, vv_mst_name=bands.vv_mst,
        lc_name=bands.land_cover,
        offset_vh=offset_vh, offset_vv=offset_vv,
    )

    exprs = build_snap_expressions(
        bands={
            "vh_slv": bands.vh_slv,
            "vh_mst": bands.vh_mst,
            "vv_slv": bands.vv_slv,
            "vv_mst": bands.vv_mst,
        },
        offset_vh=offset_vh,
        offset_vv=offset_vv,
        thresholds=thresholds,
    )

    return {
        "thr_forest_vv":    exprs["thr_forest_vv"],
        "thr_forest_vh":    exprs["thr_forest_vh"],
        "thr_urban_vv":     exprs["thr_urban_vv"],
        "thr_urban_vh":     exprs["thr_urban_vh"],
        "thr_open_vv":      exprs["thr_open_vv"],
        "thr_open_vh":      exprs["thr_open_vh"],
        "elev_ceiling_tif": str(elev_ceiling_tif),
        "slope_mask_tif":   str(slope_mask_tif),
        "has_data":         exprs["has_data"],
        "vh_norm":          exprs["vh_norm"],
        "vv_norm":          exprs["vv_norm"],
    }