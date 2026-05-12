from pathlib import Path
import math
import numpy as np
import rasterio
from rasterio.transform import array_bounds

from .models import ProductData
from .product_utils import get_band_file, list_bands


def compute_water_elevation_p95(stack_dim_path: Path, water_class: int = 80) -> float:
    """
    Reads elevation and ESA WorldCover land cover bands from a SNAP .dim product
    using rasterio (no snappy required), then computes the P95 elevation of
    water pixels.
    """
    available = list_bands(stack_dim_path)
    print(f"[INFO] Available bands: {available}")

    # Locate the two bands we need
    lc_band_name = next((b for b in available if "land_cover" in b.lower()), "")
    elev_band_name = next((b for b in available if "elevation" in b.lower()), "")

    if lc_band_name == "":
        print("[WARN] No land cover band found")
        return 0.0  # Can't compute water elevation without land cover info
    if elev_band_name == "":
        print("[WARN] No elevation band found")
        return 0.0  # Can't compute water elevation without elevation info

    print(f"[INFO] Using land cover band: '{lc_band_name}'")
    print(f"[INFO] Using elevation band:  '{elev_band_name}'")

    elev_img = get_band_file(stack_dim_path, elev_band_name)
    lc_img = get_band_file(stack_dim_path, lc_band_name)

    with rasterio.open(elev_img) as elev_ds:
        elevation = elev_ds.read(1).astype(np.float32)
        elev_nodata = elev_ds.nodata

    with rasterio.open(lc_img) as lc_ds:
        landcover = lc_ds.read(1)

    # Mask out no-data elevation values
    if elev_nodata is not None:
        valid_elev = elevation != elev_nodata
    else:
        valid_elev = np.isfinite(elevation)

    water_mask = (landcover == water_class) & valid_elev
    water_elevations = elevation[water_mask]

    if len(water_elevations) == 0:
        print("[WARN] No water pixels found in land cover. Cannot compute elevation threshold.")
        return 10000.0

    p95 = round(float(np.percentile(water_elevations, 95)) + 5.0)
    print(
        f"[INFO] Water elevation P95: {p95:.2f}m  "
        f"(n={len(water_elevations):,} water pixels)"
    )
    return p95


def computeFloodArea(data: ProductData) -> tuple[float, float, float]:
    """Computes the number of flood pixels, estimated pixel area in m^2, and total flood area in m^2 from the flood mask data."""
    band, transform, crs, height, width = (
        data.band,
        data.transform,
        data.crs,
        data.height,
        data.width,
    )

    # Pixels with value 1 are flood
    flood_mask = (~band.mask) & (band.data == 1)
    flood_count = int(np.count_nonzero(flood_mask))

    # --- Area calculation ---
    earth_radius_m = 6378137.0

    if crs and crs.is_geographic:
        bounds = array_bounds(height, width, transform)
        # bounds = (left, bottom, right, top)
        center_lat = (bounds[1] + bounds[3]) / 2.0
        lat_rad = math.radians(center_lat)

        meters_per_deg_lat = (math.pi / 180.0) * earth_radius_m
        meters_per_deg_lon = (math.pi / 180.0) * earth_radius_m * math.cos(lat_rad)

        px_area_m2 = abs((transform.a * meters_per_deg_lon) * (transform.e * meters_per_deg_lat))
    else:
        px_area_m2 = abs(transform.a * transform.e)

    total_area_m2 = flood_count * px_area_m2

    return flood_count, px_area_m2, total_area_m2


def displayResults(dim_path: Path, flood_count: float, px_area_m2: float, total_area_m2: float) -> None:
    print("\n--- Flood Calculation Results ---")
    print(f"Product:                  {dim_path.name}")
    print(f"Number of Flooded Pixels: {flood_count:,}")
    print(f"Estimated Pixel Size:     ~{px_area_m2:,.2f} m^2")
    print(f"Total Flooded Area:       {total_area_m2:,.2f} m^2  ({total_area_m2 / 1_000_000:.3f} km^2)\n")
