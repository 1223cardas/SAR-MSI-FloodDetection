from dataclasses import fields
from pathlib import Path
from typing import Any
import numpy as np
import re

from .masking import (
    build_snap_expressions,
    compute_adaptive_thresholds,
    compute_elevation_ceiling,
    compute_scene_offsets,
    load_scene_context,
)
from .pclasses import StackBands
from .paths import paths


def _getBandsFromStack(dimstack_file: Path) -> StackBands:
    """Parse band names from the .dim XML."""
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


# def computeWorkflowVariables(dimstack_file: Path) -> dict[str, Any]:
#     """
#     Compute all variables needed by createMask.xml using optimized one-pass I/O context.

#     Returns a dict whose keys match the ${...} parameters in the XML.
#     """
#     bands = _getBandsFromStack(dimstack_file)
#     data_folder = dimstack_file.with_suffix(".data")

#     # 1. Centralized I/O Hub — Reads all targeting bands into memory once
#     context = load_scene_context(
#         data_folder=data_folder,
#         vh_slv_name=bands.vh_slv,
#         vh_mst_name=bands.vh_mst,
#         vv_slv_name=bands.vv_slv,
#         vv_mst_name=bands.vv_mst,
#         lc_name=bands.land_cover
#     )

#     # 2. Scene normalization offsets using cached permanent water pixels
#     offset_vh, offset_vv = compute_scene_offsets(context)

#     # 3. Calculate local spatial thresholds filtered via urban distribution
#     thresholds = compute_adaptive_thresholds(
#         context=context,
#         offset_vh=offset_vh,
#         offset_vv=offset_vv
#     )

#     # 4. Generate dynamic auxiliary terrain files
#     elev_ceiling_tif = compute_elevation_ceiling(
#         data_folder,
#         elev_name=bands.elevation,
#         lc_name=bands.land_cover,
#         out_tif=paths["cache"] / "elev_ceiling.tif",
#     )

#     # 5. Compile mathematical nodes mapping directly into SNAP engine specs
#     exprs = build_snap_expressions(
#         bands={
#             "vh_slv": bands.vh_slv,
#             "vh_mst": bands.vh_mst,
#             "vv_slv": bands.vv_slv,
#             "vv_mst": bands.vv_mst,
#         },
#         offset_vh=offset_vh,
#         offset_vv=offset_vv,
#         thresholds=thresholds,
#     )

#     return {
#         "thr_forest_vv":    exprs["thr_forest_vv"],
#         "thr_forest_vh":    exprs["thr_forest_vh"],
#         "thr_urban_vv":     exprs["thr_urban_vv"],
#         "thr_urban_vh":     exprs["thr_urban_vh"],
#         "thr_open_vv":      exprs["thr_open_vv"],
#         "thr_open_vh":      exprs["thr_open_vh"],
#         "elev_ceiling_tif": str(elev_ceiling_tif),
#         "has_data":         exprs["has_data"],
#         "vh_norm":          exprs["vh_norm"],
#         "vv_norm":          exprs["vv_norm"],
#     }


def computeWorkflowVariables(dimstack_file: Path) -> dict[str, Any]:
    print("\n" + "="*60)
    print("  COMPUTING WORKFLOW VARIABLES")
    print("="*60)

    bands = _getBandsFromStack(dimstack_file)
    print(f"\n[1/5] Bands identified from stack:")
    print(f"|\t VH master : {bands.vh_mst}")
    print(f"|\t VH slave  : {bands.vh_slv}")
    print(f"|\t VV master : {bands.vv_mst}")
    print(f"|\t VV slave  : {bands.vv_slv}")
    print(f"|\t Elevation : {bands.elevation}")
    print(f"|\t Land Cover: {bands.land_cover}")

    data_folder = dimstack_file.with_suffix(".data")

    # 1. Centralized I/O Hub
    print(f"\n[2/5] Loading scene bands from: {data_folder.name}")
    context = load_scene_context(
        data_folder=data_folder,
        vh_slv_name=bands.vh_slv,
        vh_mst_name=bands.vh_mst,
        vv_slv_name=bands.vv_slv,
        vv_mst_name=bands.vv_mst,
        lc_name=bands.land_cover
    )

    lc = context["lc"]
    unique, counts = np.unique(lc[lc > 0], return_counts=True)
    total_px = counts.sum()
    lc_labels = {10: "Trees", 20: "Shrubland", 30: "Grassland", 40: "Cropland",
                 50: "Built-up", 60: "Bare", 70: "Snow/Ice", 80: "Water",
                 90: "Herbaceous", 95: "Mangrove", 100: "Moss"}
    print(f"|\t Land cover distribution ({total_px:,} valid pixels):")
    for cls, cnt in zip(unique, counts):
        label = lc_labels.get(int(cls), f"Class {cls}")
        pct = 100.0 * cnt / total_px
        print(f"|\t   [{int(cls):3d}] {label:<12} → {cnt:>8,} px  ({pct:5.1f}%)")

    # 2. Scene normalization offsets
    print(f"\n[3/5] Computing scene normalization offsets...")
    offset_vh, offset_vv = compute_scene_offsets(context)
    print(f"|\t Final offsets → VH: {offset_vh:+.4f} dB  |  VV: {offset_vv:+.4f} dB")

    # 3. Adaptive thresholds
    print(f"\n[4/5] Computing adaptive thresholds...")
    thresholds = compute_adaptive_thresholds(
        context=context,
        offset_vh=offset_vh,
        offset_vv=offset_vv
    )
    print(f"|\t Thresholds summary:")
    for name, (thr_vh, thr_vv) in thresholds.items():
        print(f"|\t   {name:<12} → VH < {float(thr_vh):+.4f}  |  VV < {float(thr_vv):+.4f}")

    # 4. Elevation ceiling
    print(f"\n[5/5] Computing elevation ceiling...")
    elev_ceiling_tif = compute_elevation_ceiling(
        data_folder,
        elev_name=bands.elevation,
        lc_name=bands.land_cover,
        out_tif=paths["cache"] / "elev_ceiling.tif",
    )
    print(f"|\t Elevation ceiling TIF → {elev_ceiling_tif.name}")

    # 5. SNAP expressions
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

    print(f"\n  SNAP expressions compiled:")
    print(f"|\t has_data  : {exprs['has_data']}")
    print(f"|\t vh_norm   : {exprs['vh_norm']}")
    print(f"|\t vv_norm   : {exprs['vv_norm']}")
    print("="*60 + "\n")

    return {
        "thr_forest_vv":    exprs["thr_forest_vv"],
        "thr_forest_vh":    exprs["thr_forest_vh"],
        "thr_urban_vv":     exprs["thr_urban_vv"],
        "thr_urban_vh":     exprs["thr_urban_vh"],
        "thr_open_vv":      exprs["thr_open_vv"],
        "thr_open_vh":      exprs["thr_open_vh"],
        "elev_ceiling_tif": str(elev_ceiling_tif),
        "has_data":         exprs["has_data"],
        "vh_norm":          exprs["vh_norm"],
        "vv_norm":          exprs["vv_norm"],
    }