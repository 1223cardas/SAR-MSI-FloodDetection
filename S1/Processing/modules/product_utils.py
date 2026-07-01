# from typing import Any
# from pathlib import Path
# from dataclasses import fields
# import re, math

# from .raster_utils import (
#     compute_water_elevation_p95,
#     compute_water_class_logratio_ceiling,
#     compute_tile_threshold_tif,
#     compute_slope_mask_tif,
#     export_logratio_tif,
# )
# from .utils import get_band_file
# from .pclasses import StackBands
# from .paths import paths


# def getBandsFromStack(dimstack_file: Path) -> StackBands:
#     with open(dimstack_file, "r", encoding="ISO-8859-1") as f:
#         content = f.read()

#     bands: list[str] = re.findall(r"<BAND_NAME>(.*?)</BAND_NAME>", content)

#     stackbands = StackBands()
#     for b in bands:
#         b_lower = b.lower()
#         for field in fields(StackBands):
#             if field.name in b_lower:
#                 setattr(stackbands, field.name, b)
#                 break

#     missing = [
#         field.name
#         for field in fields(StackBands)
#         if getattr(stackbands, field.name) == ""
#     ]

#     if missing:
#         raise ValueError(
#             "Could not extract all variable names from stack product.\n"
#             f"Missing: {', '.join(missing)}\n"
#             "Check that the stack was created correctly and band names are present."
#         )

#     return stackbands


# def compileLogRatioExpressions(bands: StackBands) -> tuple[str, str, str]:
#     """
#     Build SNAP BandMaths expressions for the log-ratio change signal and the
#     data-validity guard.

#     Log-ratio in dB:
#         10 * log10(slave) - 10 * log10(master)

#     SNAP BandMaths uses natural log (log()), so we convert:
#         10/ln(10) * (log(slave) - log(master))   ≈   4.34294 * log(slave/master)

#     A negative value means backscatter dropped after the event — the expected
#     flood signature for open water and bare flooded soil.
#     The threshold TIFs produced by compute_tile_threshold_tif are in the same
#     dB units, so the comparison in createMask.xml is directly meaningful.
#     """
#     # SNAP log() is natural log. 10/ln(10) ≈ 4.342944819
#     log10_factor = "4.342944819"

#     vh_log_ratio = (
#         f"({log10_factor} * log({bands.vh_slv} / {bands.vh_mst}))"
#     )
#     vv_log_ratio = (
#         f"({log10_factor} * log({bands.vv_slv} / {bands.vv_mst}))"
#     )

#     has_data_at_pixel = (
#         f"( ({bands.vh_slv} > 0 AND {bands.vh_mst} > 0)"
#         f" AND ({bands.vv_slv} > 0 AND {bands.vv_mst} > 0) )"
#     )

#     return vh_log_ratio, vv_log_ratio, has_data_at_pixel


# def ensureLogRatioTIFexists(data_folder: Path, bands: StackBands) -> tuple[Path, Path]:
#     """
#     Ensure the VH and VV log-ratio GeoTIFFs exist in the cache.
#     Creates them via export_logratio_tif if missing.
#     """
#     vh_logratio_tif = paths["cache"] / "vh_logratio.tif"
#     vv_logratio_tif = paths["cache"] / "vv_logratio.tif"

#     if not vh_logratio_tif.exists():
#         print("|\tExporting VH log-ratio TIF...")
#         export_logratio_tif(data_folder, [bands.vh_slv, bands.vh_mst], vh_logratio_tif)

#     if not vv_logratio_tif.exists():
#         print("|\tExporting VV log-ratio TIF...")
#         export_logratio_tif(data_folder, [bands.vv_slv, bands.vv_mst], vv_logratio_tif)

#     return vh_logratio_tif, vv_logratio_tif


# def ensureThresholdSurfaceExists(
#     vh_logratio_tif: Path,
#     vv_logratio_tif: Path,
#     lc_img: Path,
# ) -> tuple[Path, Path]:
#     """
#     Ensure the VH and VV GMM threshold surfaces exist in the cache.

#     The ceiling for each polarisation is derived from the log-ratio values of
#     permanent water pixels (ESA WorldCover class 80). This prevents the GMM
#     valley threshold from being set above the typical log-ratio of known water
#     — which would cause non-flood pixels to be classified as flood.
#     """
#     vh_threshold_tif = paths["cache"] / "vh_threshold.tif"
#     vv_threshold_tif = paths["cache"] / "vv_threshold.tif"

#     # Ceiling computed from permanent water pixels in each polarisation
#     vh_ceiling = compute_water_class_logratio_ceiling(str(vh_logratio_tif), str(lc_img))
#     vv_ceiling = compute_water_class_logratio_ceiling(str(vv_logratio_tif), str(lc_img))

#     if not vh_threshold_tif.exists():
#         print("|\tComputing VH threshold surface (GMM, log-ratio)...")
#         compute_tile_threshold_tif(
#             vh_logratio_tif,
#             str(vh_threshold_tif),
#             max_threshold_db=vh_ceiling,
#         )

#     if not vv_threshold_tif.exists():
#         print("|\tComputing VV threshold surface (GMM, log-ratio)...")
#         compute_tile_threshold_tif(
#             vv_logratio_tif,
#             str(vv_threshold_tif),
#             max_threshold_db=vv_ceiling,
#         )

#     return vh_threshold_tif, vv_threshold_tif


# def computeWorkflowVariables(dimstack_file: Path) -> dict[str, Any]:
#     """
#     Compute all dynamic, per-scene variables needed by createMask.xml.

#     Returns a dict whose keys match the ${...} parameter names in the XML:
#       - elev_threshold_tif  — spatially adaptive elevation ceiling (metres)
#       - vh_threshold_tif    — VH GMM log-ratio threshold surface (dB)
#       - vv_threshold_tif    — VV GMM log-ratio threshold surface (dB)
#       - slope_mask_tif      — binary mask, 1 where slope < 15°
#       - hasDataAtPixel      — SNAP BandMaths guard expression
#       - vh_diff             — SNAP BandMaths VH log-ratio expression (dB)
#       - vv_diff             — SNAP BandMaths VV log-ratio expression (dB)
#     """
#     bands = getBandsFromStack(dimstack_file)
#     vh_log_ratio_expr, vv_log_ratio_expr, has_data_at_pixel = compileLogRatioExpressions(bands)

#     data_folder = dimstack_file.with_suffix(".data")

#     # 1. Elevation threshold surface
#     elev_threshold_tif = compute_water_elevation_p95(
#         data_folder, [bands.elevation, bands.land_cover]
#     )

#     # 2. Log-ratio TIFs (the actual change images, in dB)
#     vh_logratio_tif, vv_logratio_tif = ensureLogRatioTIFexists(data_folder, bands)

#     # 3. GMM threshold surfaces (adaptive, bimodality-tested)
#     lc_img = get_band_file(data_folder, bands.land_cover)
#     vh_threshold_tif, vv_threshold_tif = ensureThresholdSurfaceExists(
#         vh_logratio_tif, vv_logratio_tif, lc_img
#     )

#     # 4. Slope mask
#     slope_mask_tif = paths["cache"] / "slope_mask.tif"
#     if not slope_mask_tif.exists():
#         print("|\tComputing slope mask...")
#         elev_img = get_band_file(data_folder, bands.elevation)
#         compute_slope_mask_tif(elev_img, slope_mask_tif)

#     return {
#         "elev_threshold_tif": str(elev_threshold_tif),
#         "vh_threshold_tif":   str(vh_threshold_tif),
#         "vv_threshold_tif":   str(vv_threshold_tif),
#         "slope_mask_tif":     str(slope_mask_tif),
#         "hasDataAtPixel":     has_data_at_pixel,
#         "vh_diff":            vh_log_ratio_expr,
#         "vv_diff":            vv_log_ratio_expr,
#     }

# product_utils.py  — stripped down, keep only this:

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
        "elev_ceiling_tif": str(elev_ceiling_tif),
        "slope_mask_tif":   str(slope_mask_tif),
        "has_data":         exprs["has_data"],
        "vh_norm":          exprs["vh_norm"],
        "vv_norm":          exprs["vv_norm"],
        "thr_urban_vv":     exprs["thr_urban_vv"],
        "thr_urban_vh":     exprs["thr_urban_vh"],
        "thr_open_vv":      exprs["thr_open_vv"],
        "thr_open_vh":      exprs["thr_open_vh"],
        "thr_forest_vv":    exprs["thr_forest_vv"],
        "thr_forest_vh":    exprs["thr_forest_vh"],
        "thr_urban_vv":     exprs["thr_urban_vv"],
        "thr_urban_vh":     exprs["thr_urban_vh"],
    }