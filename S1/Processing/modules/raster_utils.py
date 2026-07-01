from typing import Iterator
from pathlib import Path
import numpy as np
import rasterio
import math

from rasterio.transform import array_bounds
from rasterio.windows import Window
from scipy import ndimage
from scipy.ndimage import gaussian_filter, label
from scipy.interpolate import griddata
from scipy.stats import norm as scipy_norm
from sklearn.mixture import GaussianMixture
from .pclasses import ProductData
from .utils import get_band_file
from .paths import build_cache_file


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

def isValidMask(arr: np.ndarray, nodata=None) -> np.ndarray:
    mask = np.isfinite(arr)
    if nodata is not None:
        mask &= arr != nodata
    return mask


def updateGtiffMeta(meta: dict, dtype) -> dict:
    meta = meta.copy()
    meta.update(driver="GTiff", dtype=dtype, count=1,
                compress="deflate", tiled=True, blockxsize=512, blockysize=512)
    return meta


def iterateTiles(height: int, width: int, tile_size: int) -> Iterator[tuple[int, int, int, int]]:
    for row in range(0, height, tile_size):
        for col in range(0, width, tile_size):
            yield row, col, min(tile_size, height - row), min(tile_size, width - col)


def interpolateSurface(
    height: int, width: int,
    points: np.ndarray, values: list[float],
    sigma: float = 3.0, method: str = "linear",
) -> np.ndarray:
    """Interpolate sparse tile control-point values to a full raster, then Gaussian-smooth."""
    grid_y, grid_x = np.mgrid[0:height, 0:width]
    fallback = float(np.median(values))
    if len(values) >= 4:
        surface = griddata(points, values, (grid_y, grid_x), method=method, fill_value=fallback)
    else:
        surface = np.full((height, width), fallback, dtype=np.float32)
    return gaussian_filter(surface.astype(np.float32), sigma=sigma)


def geographic_resolution_to_meters(transform, latitude_deg: float) -> tuple[float, float]:
    R = 6378137.0
    lat_rad = math.radians(latitude_deg)
    return (
        abs(transform.a) * math.pi / 180.0 * R * math.cos(lat_rad),
        abs(transform.e) * math.pi / 180.0 * R,
    )


# ---------------------------------------------------------------------------
# Log-ratio change image
# ---------------------------------------------------------------------------

def export_logratio_tif(data_folder: Path, slv_mst: list[str], out_tif: Path) -> None:
    """
    Compute the log-ratio change image between two SAR sigma-nought bands:
        log_ratio = 10*log10(slave) - 10*log10(master)  [dB]

    Negative values = backscatter drop (open water, flooded bare soil).
    Streamed in 512-row blocks to keep memory use low.
    """
    slv_img = get_band_file(data_folder, slv_mst[0])
    mst_img = get_band_file(data_folder, slv_mst[1])

    with rasterio.open(slv_img) as slv_ds, rasterio.open(mst_img) as mst_ds:
        if slv_ds.shape != mst_ds.shape:
            raise ValueError(
                f"Slave/master shapes do not match: {slv_ds.shape} vs {mst_ds.shape}"
            )
        meta = updateGtiffMeta(slv_ds.meta.copy(), rasterio.float32)
        h, w = slv_ds.height, slv_ds.width

        with rasterio.open(out_tif, "w", **meta) as dst:
            for row in range(0, h, 512):
                window = Window(0, row, w, min(512, h - row))
                slv_arr = slv_ds.read(1, window=window).astype(np.float32)
                mst_arr = mst_ds.read(1, window=window).astype(np.float32)

                valid = (
                    (slv_arr > 0) & (mst_arr > 0)
                    & np.isfinite(slv_arr) & np.isfinite(mst_arr)
                )
                if slv_ds.nodata is not None:
                    valid &= slv_arr != slv_ds.nodata
                if mst_ds.nodata is not None:
                    valid &= mst_arr != mst_ds.nodata

                out = np.full(slv_arr.shape, np.nan, dtype=np.float32)
                out[valid] = 10.0 * np.log10(slv_arr[valid]) - 10.0 * np.log10(mst_arr[valid])
                dst.write(out, 1, window=window)


# ---------------------------------------------------------------------------
# GMM bimodality test (Chini et al. 2017)
# ---------------------------------------------------------------------------

def _test_tile_bimodality(
    vals: np.ndarray,
    min_ashman_d: float = 2.0,
    min_surface_ratio: float = 0.05,
) -> tuple[bool, float | None]:
    """
    Fit a 2-component GMM and accept the tile only if it is genuinely bimodal:
      - Ashman D >= 2.0: the two modes are clearly separated
      - Surface ratio >= 5%: neither class is negligibly small

    Returns (True, valley_threshold) if bimodal, otherwise (False, None).
    The valley threshold is the GMM PDF minimum between the two modes.
    """
    if len(vals) < 50:
        return False, None

    gmm = GaussianMixture(n_components=2, covariance_type="full",
                          random_state=0, max_iter=300, n_init=3)
    try:
        gmm.fit(vals.reshape(-1, 1))
    except Exception:
        return False, None

    mu = [float(gmm.means_[i, 0]) for i in range(2)]
    s  = [float(np.sqrt(gmm.covariances_[i, 0, 0])) for i in range(2)]
    w  = list(gmm.weights_)

    if any(si < 1e-6 for si in s):
        return False, None

    lower_mode_mean = min(mu[0], mu[1])
    if lower_mode_mean > -3.5:
        return False, None

    # Criterion 1: Ashman D — modes must be clearly separated
    ashman_d = np.sqrt(2.0) * abs(mu[0] - mu[1]) / np.sqrt(s[0]**2 + s[1]**2)
    if ashman_d < min_ashman_d:
        return False, None

    # Criterion 2: surface ratio — neither class should be negligibly small
    if min(w) / max(w) < min_surface_ratio:
        return False, None

    # Threshold = GMM PDF valley between the two modes
    lo, hi = min(mu), max(mu)
    x = np.linspace(lo, hi, 200)
    pdf = sum(w[i] * scipy_norm.pdf(x, mu[i], s[i]) for i in range(2))
    thr = float(x[np.argmin(pdf)])

    return True, thr


# ---------------------------------------------------------------------------
# Elevation threshold surface
# ---------------------------------------------------------------------------

def compute_water_elevation_p95(
    data_file: Path, vars: list[str],
    water_class: int = 80, tile_size: int = 512,
) -> Path:
    """
    Build a spatially adaptive elevation ceiling raster from permanent water
    pixels (ESA WorldCover class 80). Each tile contributes its P95 elevation
    of water pixels; values are interpolated to a full-resolution surface.
    """
    elev_band_name, lc_band_name = vars

    with rasterio.open(get_band_file(data_file, elev_band_name)) as elev_ds:
        elevation  = elev_ds.read(1).astype(np.float32)
        meta       = elev_ds.meta.copy()
        h, w       = elev_ds.height, elev_ds.width
        valid_elev = isValidMask(elevation, elev_ds.nodata)

    with rasterio.open(get_band_file(data_file, lc_band_name)) as lc_ds:
        landcover = lc_ds.read(1)

    centers_y, centers_x, thresholds = [], [], []

    for row, col, win_h, win_w in iterateTiles(h, w, tile_size):
        water_elev = elevation[row:row+win_h, col:col+win_w][
            (landcover[row:row+win_h, col:col+win_w] == water_class)
            & valid_elev[row:row+win_h, col:col+win_w]
        ]
        if water_elev.size < 10:
            continue
        thresholds.append(float(np.percentile(water_elev, 95)))
        centers_y.append(row + win_h / 2)
        centers_x.append(col + win_w / 2)

    if not thresholds:
        raise RuntimeError("No water pixels found — cannot compute elevation threshold.")

    print(f"|\tElevation threshold: {len(thresholds)} tiles, "
          f"range [{min(thresholds):.1f}, {max(thresholds):.1f}] m")

    surface = interpolateSurface(h, w, np.column_stack([centers_y, centers_x]), thresholds)

    out_path = build_cache_file("elev_threshold.tif")
    if not out_path.exists():
        with rasterio.open(out_path, "w", **updateGtiffMeta(meta, rasterio.float32)) as dst:
            dst.write(surface, 1)
    return out_path


# ---------------------------------------------------------------------------
# Permanent-water ceiling for the GMM threshold surface
# ---------------------------------------------------------------------------

def compute_water_class_logratio_ceiling(
    logratio_tif: str, lc_img: str, water_class: int = 80,
) -> float | None:
    """
    Derive the GMM threshold ceiling from permanent water pixels (class 80):
        ceiling = median(water log-ratio) - 2 dB,  clamped to >= -8 dB.

    This prevents the GMM valley from being set above the log-ratio of known
    permanent water, which would misclassify non-flood pixels as flood.
    Returns None if fewer than 100 water pixels are found (no ceiling applied).
    """
    with rasterio.open(logratio_tif) as ds:
        diff = ds.read(1).astype(np.float32)
    with rasterio.open(lc_img) as ds:
        lc = ds.read(1)

    water_vals = diff[(lc == water_class) & np.isfinite(diff)]

    if water_vals.size < 100:
        print(f"|\t[WARN] Only {water_vals.size} permanent water pixels — no ceiling applied.")
        return None

    median_water = float(np.percentile(water_vals, 50))
    ceiling = max(median_water - 2.0, -8.0)
    print(f"|\tWater log-ratio median: {median_water:+.2f} dB → ceiling: {ceiling:+.2f} dB")
    return ceiling


# ---------------------------------------------------------------------------
# Tile-wise GMM threshold surface
# ---------------------------------------------------------------------------

def compute_tile_threshold_tif(
    src_band_path: Path,
    out_tif: str,
    min_pixels: int = 100,
    max_threshold_db: float | None = None,
    min_ashman_d: float = 2.0,
    min_surface_ratio: float = 0.05,
) -> str:
    """
    Build a spatially adaptive flood-detection threshold surface using tile-wise
    2-component GMM fitting (Chini et al. 2017).

    Only bimodally valid tiles (Ashman D >= min_ashman_d, surface ratio >= min_surface_ratio)
    contribute. Tiles whose GMM valley exceeds max_threshold_db are discarded.
    Accepted thresholds are interpolated to a full raster and Gaussian-smoothed.
    """

    with rasterio.open(src_band_path) as src:
        meta    = src.meta.copy()
        h, w    = src.height, src.width
        nodata  = src.nodata

    tile_size = int(np.clip(min(h, w)/8, 256, 1024))
    centers_y, centers_x, tile_thresholds = [], [], []

    with rasterio.open(src_band_path) as src:
        for row in range(0, h, tile_size):
            for col in range(0, w, tile_size):
                win_h, win_w = min(tile_size, h - row), min(tile_size, w - col)
                arr  = src.read(1, window=Window(col, row, win_w, win_h)).astype(np.float32)
                valid = np.isfinite(arr)
                if nodata is not None:
                    valid &= arr != nodata
                vals = arr[valid]

                if len(vals) < min_pixels:
                    continue

                is_bimodal, thr = _test_tile_bimodality(vals, min_ashman_d, min_surface_ratio)
                if not is_bimodal or thr is None:
                    continue
                if max_threshold_db is not None and thr > max_threshold_db:
                    continue

                centers_y.append(row + win_h / 2)
                centers_x.append(col + win_w / 2)
                tile_thresholds.append(thr)

    print(f"|\tThreshold surface: {len(tile_thresholds)} bimodal tiles accepted")

    if not tile_thresholds:
        if max_threshold_db is not None:
            print("|\t[WARN] No bimodal tiles with ceiling — retrying without ceiling.")
            return compute_tile_threshold_tif(
                src_band_path, out_tif, tile_size, min_pixels,
                None, min_ashman_d, min_surface_ratio,
            )
        print("|\t[WARN] No bimodal tiles found — using -3 dB conservative fallback.")
        surface = np.full((h, w), -3.0, dtype=np.float32)
    else:
        surface = interpolateSurface(
            h, w,
            np.column_stack([centers_y, centers_x]),
            tile_thresholds,
            sigma=1.5,
        )

    with rasterio.open(out_tif, "w", **updateGtiffMeta(meta, rasterio.float32)) as dst:
        dst.write(surface, 1)

    return out_tif


# ---------------------------------------------------------------------------
# Flood area calculation
# ---------------------------------------------------------------------------

def computeFloodArea(data: ProductData) -> tuple[float, float, float]:
    """Compute flood pixel count, pixel area (m²), and total flooded area (m²)."""
    flood_mask  = (~data.band.mask) & (data.band.data == 1)
    clean_mask  = ndimage.binary_opening(flood_mask, structure=np.ones((3, 3)))
    flood_count = int(np.count_nonzero(clean_mask))

    if data.crs and data.crs.is_geographic:
        bounds      = array_bounds(data.height, data.width, data.transform)
        lat_rad     = math.radians((bounds[1] + bounds[3]) / 2.0)
        R           = 6378137.0
        m_per_deg_lon = math.pi / 180.0 * R * math.cos(lat_rad)
        m_per_deg_lat = math.pi / 180.0 * R
        px_area_m2  = abs(data.transform.a * m_per_deg_lon * data.transform.e * m_per_deg_lat)
    else:
        px_area_m2  = abs(data.transform.a * data.transform.e)

    return flood_count, px_area_m2, flood_count * px_area_m2


# ---------------------------------------------------------------------------
# Slope mask
# ---------------------------------------------------------------------------

def compute_slope_mask_tif(elev_img: Path, out_tif: Path, max_slope_deg: float = 15.0) -> None:
    """Binary slope mask derived from DEM: 1 where slope < max_slope_deg, 0 elsewhere."""
    with rasterio.open(elev_img) as src:
        elev   = src.read(1).astype(np.float32)
        meta   = src.meta.copy()
        nodata = src.nodata
        res_x, res_y = abs(src.transform.a), abs(src.transform.e)
        if src.crs and src.crs.is_geographic:
            centre_lat = (src.bounds.bottom + src.bounds.top) / 2.0
            res_x, res_y = geographic_resolution_to_meters(src.transform, centre_lat)

    elev[~isValidMask(elev, nodata)] = np.nan
    slope_deg = np.degrees(np.arctan(np.sqrt(
        np.gradient(elev, res_x, axis=1)**2 + np.gradient(elev, res_y, axis=0)**2
    )))

    mask = np.where(np.isfinite(slope_deg) & (slope_deg < max_slope_deg), 1, 0).astype(np.uint8)

    meta = updateGtiffMeta(meta, rasterio.uint8)
    meta["nodata"] = None
    with rasterio.open(out_tif, "w", **meta) as dst:
        dst.write(mask, 1)
    print(f"|\tSlope mask written (threshold: {max_slope_deg}°)")


# ---------------------------------------------------------------------------
# Final flood export
# ---------------------------------------------------------------------------

def convertFileToTif(flood_dim: Path, out_tif: Path) -> None:
    data_folder = Path(str(flood_dim).replace(".dim", ".data"))
    with rasterio.open(get_band_file(data_folder, "Flood")) as src:
        data = src.read(1)
        meta = src.meta.copy()

    # Determine valid data area (not NaN in source)
    valid = np.isfinite(data)

    # Morphological cleanup — only on valid pixels
    flood_pixels = valid & (data == 1)
    clean = ndimage.binary_opening(flood_pixels, structure=np.ones((5, 5)))

    # Remove small blobs
    labeled, n = label(clean)
    if n > 0:
        sizes = ndimage.sum(clean, labeled, range(1, n + 1))
        clean[np.isin(labeled, np.where(sizes < 50)[0] + 1)] = False

    # Build output: 1=flood, 0=no flood, 255=nodata (outside scene)
    out = np.full(data.shape, 255, dtype=np.uint8)   # start as nodata
    out[valid] = 0                                     # valid area = no flood
    out[clean] = 1                                     # detected flood

    meta.update(
        driver="GTiff",
        dtype=rasterio.uint8,
        count=1,
        compress="deflate",
        tiled=True,
        blockxsize=512,
        blockysize=512,
        nodata=255,
    )
    with rasterio.open(out_tif, "w", **meta) as dst:
        dst.write(out, 1)
    print(f"|\tFlood mask exported to: {out_tif}")


def displayResults(dim_path: Path, flood_count: float, px_area_m2: float, total_area_m2: float) -> None:
    print("\n--- Flood Calculation Results ---")
    print(f"Product:                  {dim_path.name}")
    print(f"Number of Flooded Pixels: {flood_count:,}")
    print(f"Estimated Pixel Size:     ~{px_area_m2:,.2f} m²")
    print(f"Total Flooded Area:       {total_area_m2:,.2f} m²  ({total_area_m2 / 1_000_000:.3f} km²)")