import os

import rasterio

from config import NODATA_VALUE
from preview import save_preview_png, show_preview_window
from processing import (
    compute_binary_area,
    compute_ndwi,
    compute_optimal_threshold,
    flood_map,
    water_mask,
)
from raster_io import debug, ensure_alignment, prepare_workspace, stats, write_raster


def _print_area(label, area_m2):
    print(f"{label}: {area_m2:,.2f} m2 ({area_m2 / 1_000_000.0:,.4f} km2)")


def run_pipeline(b3b_path, b8b_path, b3a_path, b8a_path, work, preview=False, threshold=None):
    prepare_workspace(work)

    with rasterio.open(b3b_path) as ref_src:
        b3b_data = ref_src.read(1).astype("float32")
        profile = ref_src.profile.copy()

        b8b_data = ensure_alignment(ref_src, b8b_path)
        b3a_data = ensure_alignment(ref_src, b3a_path)
        b8a_data = ensure_alignment(ref_src, b8a_path)

    print("\nShapes:")
    print(b3b_data.shape, b8b_data.shape, b3a_data.shape, b8a_data.shape)

    debug("NDWI")
    ndwi_before = compute_ndwi(b3b_data, b8b_data)
    ndwi_after = compute_ndwi(b3a_data, b8a_data)

    write_raster(os.path.join(work, "ndwi_before.tif"), ndwi_before, profile, NODATA_VALUE)
    write_raster(os.path.join(work, "ndwi_after.tif"), ndwi_after, profile, NODATA_VALUE)

    stats(ndwi_before, "NDWI BEFORE", NODATA_VALUE)
    stats(ndwi_after, "NDWI AFTER", NODATA_VALUE)

    if threshold is None:
        threshold = compute_optimal_threshold(ndwi_before, ndwi_after)
        print(f"\nThreshold mode: AUTO (Otsu) -> {threshold:.4f}")
    else:
        print(f"\nThreshold mode: MANUAL -> {threshold:.4f}")

    debug("WATER MASK")
    water_before = water_mask(ndwi_before, threshold=threshold)
    water_after = water_mask(ndwi_after, threshold=threshold)

    write_raster(os.path.join(work, "water_before.tif"), water_before, profile, 0)
    write_raster(os.path.join(work, "water_after.tif"), water_after, profile, 0)

    stats(water_before, "WATER BEFORE", 0)
    stats(water_after, "WATER AFTER", 0)

    debug("FLOOD")
    flood = flood_map(water_after, water_before)

    write_raster(os.path.join(work, "flood.tif"), flood, profile, 0)
    stats(flood, "NEW FLOOD", 0)

    debug("AREA")
    transform = profile["transform"]
    area_before = compute_binary_area(water_before, transform)
    area_after = compute_binary_area(water_after, transform)
    area_flood = compute_binary_area(flood, transform)
    _print_area("Water BEFORE", area_before)
    _print_area("Water AFTER ", area_after)
    _print_area("New FLOOD   ", area_flood)

    if preview:
        preview_path = os.path.join(work, "preview.png")
        save_preview_png(
            preview_path,
            ndwi_before,
            ndwi_after,
            water_before,
            water_after,
            flood,
            threshold=threshold,
        )
        print("Preview image:", os.path.abspath(preview_path))
        show_preview_window(
            ndwi_before,
            ndwi_after,
            water_before,
            water_after,
            flood,
            threshold=threshold,
        )

    print("\nDONE ->", os.path.abspath(work))
