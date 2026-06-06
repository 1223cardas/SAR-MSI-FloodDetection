from pathlib import Path
import math
import numpy as np
import rasterio
from rasterio.transform import array_bounds
from skimage.filters import threshold_otsu

from .pclasses import ProductData
from .product_utils import get_band_file


def compute_water_elevation_p95(data_file: Path, vars: list[str], water_class: int = 80) -> float:
    """Read elevation and ESA WorldCover land cover bands to compute the P95 elevation of water pixels."""
    elev_band_name, lc_band_name = vars

    if lc_band_name == "":
        print("[WARN] No land cover band found")
        return 1e6
    if elev_band_name == "":
        print("[WARN] No elevation band found")
        return 1e6

    elev_img = get_band_file(data_file, elev_band_name)
    lc_img = get_band_file(data_file, lc_band_name)

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
        return 1e6

    p95 = round(float(np.percentile(water_elevations, 95)) + 5.0)
    print(f"|\tComputed elevation threshold (95th percentile): {p95:.2f} m")

    return p95


def compute_log_diff(
    slv: np.ndarray,
    mst: np.ndarray,
    slv_nodata: float | None,
    mst_nodata: float | None,
) -> np.ndarray:
    """Compute the log-ratio difference between slave and master arrays, masking out invalid pixels."""

    # Pixels must be positive and finite in both arrays for log10 to be valid.
    # Nodata sentinels are also excluded — they are not real backscatter values.
    valid = (slv > 0) & (mst > 0) & np.isfinite(slv) & np.isfinite(mst)
    if slv_nodata is not None:
        valid &= slv != slv_nodata
    if mst_nodata is not None:
        valid &= mst != mst_nodata

    if not np.any(valid):
        return np.empty(0, dtype=np.float32)

    diff = 10.0 * np.log10(slv[valid]) - 10.0 * np.log10(mst[valid])
    return diff[np.isfinite(diff)].astype(np.float32)


def compute_otsu_threshold(
    data_file: Path,
    slv_band: str,
    mst_band: str,
    label: str,
    default_threshold: float = -3.0,
) -> float:
    """Compute an Otsu threshold on the log-ratio diff between slave and master bands."""
    slv_img = get_band_file(data_file, slv_band)
    mst_img = get_band_file(data_file, mst_band)

    # Collect valid diff values block-by-block to avoid loading the entire raster into memory.
    chunks: list[np.ndarray] = []
    with rasterio.open(slv_img) as slv_ds, rasterio.open(mst_img) as mst_ds:
        if slv_ds.shape != mst_ds.shape:
            raise ValueError(f"{label} master/slave shapes do not match")

        for _, window in slv_ds.block_windows(1):
            slv = slv_ds.read(1, window=window).astype(np.float32)
            mst = mst_ds.read(1, window=window).astype(np.float32)
            diff = compute_log_diff(slv, mst, slv_ds.nodata, mst_ds.nodata)
            if diff.size > 0:
                chunks.append(diff)

    if not chunks:
        print(f"[WARN] No valid {label} diff samples for Otsu; using default.")
        return default_threshold

    all_diffs = np.concatenate(chunks)
    if all_diffs.size < 32:
        print(f"[WARN] Not enough valid {label} diff samples for Otsu; using default.")
        return default_threshold

    threshold = float(threshold_otsu(all_diffs))
    if not np.isfinite(threshold):
        print(f"[WARN] Otsu threshold invalid for {label}; using default.")
        return default_threshold
    
    print(f"|\tComputed Otsu threshold for {label} diff: {threshold:.2f} dB")

    return threshold


def compute_otsu_threshold_vh_diff(data_file: Path, vh_slv_band: str, vh_mst_band: str) -> float:
    """Compute an Otsu threshold on the VH log-ratio diff."""
    return compute_otsu_threshold(data_file, vh_slv_band, vh_mst_band, label="VH")


def compute_otsu_threshold_vv_diff(data_file: Path, vv_slv_band: str, vv_mst_band: str) -> float:
    """Compute an Otsu threshold on the VV log-ratio diff."""
    return compute_otsu_threshold(data_file, vv_slv_band, vv_mst_band, label="VV")


def computeFloodArea(data: ProductData) -> tuple[float, float, float]:
    """Compute flood pixel count, pixel area, and total area from the flood mask data."""
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
    print(f"Total Flooded Area:       {total_area_m2:,.2f} m^2  ({total_area_m2 / 1_000_000:.3f} km^2)\n"
    )
