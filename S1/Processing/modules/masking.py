import math
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.transform import array_bounds
from scipy import ndimage
from scipy.interpolate import griddata
from scipy.ndimage import gaussian_filter, label

from .pclasses import ProductData

# ── HELPERS ─────────────────────────────────────────────────────────────────

def _read_band(data_folder: Path, keyword: str) -> tuple[np.ndarray, dict, Any]:
    """Find the .img file whose name contains keyword and return (array, meta, nodata)."""
    
    matches = list(data_folder.glob(f"*{keyword}*.img"))
    if not matches:
        raise FileNotFoundError(f"No band matching '{keyword}' in {data_folder}")
    with rasterio.open(matches[0]) as ds:
        return ds.read(1).astype(np.float32), ds.meta.copy(), ds.nodata


def _logratio(slv: np.ndarray, mst: np.ndarray, slv_nd=None, mst_nd=None) -> np.ndarray:
    """Calculate 10 * log10(slave / master) in dB. Invalid pixels match NaN."""

    valid = (slv > 0) & (mst > 0) & np.isfinite(slv) & np.isfinite(mst)
    if slv_nd is not None:
        valid &= (slv != slv_nd)
    if mst_nd is not None:
        valid &= (mst != mst_nd)

    out = np.full(slv.shape, np.nan, dtype=np.float32)
    out[valid] = 10.0 * np.log10(slv[valid] / mst[valid])
    return out


def _get_geographic_pixel_area(transform: rasterio.Affine, height: int, width: int) -> tuple[float, float]:
    """Calculate dynamic resolution scales in meters for geographic (WGS84) coordinate systems."""
    bounds = array_bounds(height, width, transform)
    lat_rad = math.radians((bounds[1] + bounds[3]) / 2.0)
    r_earth = 6378137.0
    res_x = abs(transform.a) * (math.pi / 180.0) * r_earth * math.cos(lat_rad)
    res_y = abs(transform.e) * (math.pi / 180.0) * r_earth
    return res_x, res_y


# ── SCENE METRICS & THRESHOLDS ──────────────────────────────────────────────

def load_scene_context(data_folder: Path, vh_slv_name: str, vh_mst_name: str,
                       vv_slv_name: str, vv_mst_name: str, lc_name: str) -> dict[str, Any]:
    """Centralized I/O hub to read core target bands once, preventing multiple disk passes."""
    vh_slv, _, nd_vs = _read_band(data_folder, vh_slv_name)
    vh_mst, _, nd_vm = _read_band(data_folder, vh_mst_name)
    vv_slv, _, nd_ss = _read_band(data_folder, vv_slv_name)
    vv_mst, _, nd_sm = _read_band(data_folder, vv_mst_name)
    lc, _, _         = _read_band(data_folder, lc_name)
    
    return {
        "vh_slv": vh_slv, "nd_vs": nd_vs, "vh_mst": vh_mst, "nd_vm": nd_vm,
        "vv_slv": vv_slv, "nd_ss": nd_ss, "vv_mst": vv_mst, "nd_sm": nd_sm,
        "lc": lc
    }


def compute_scene_offsets(context: dict[str, Any],
                          urban_class: int = 50,
                          water_class: int = 80) -> tuple[float, float]:
    """
    Compute per-scene log-ratio offsets from urban pixels (class 50).

    Urban areas are radiometrically stable between passes in all flood 
    scenarios — including dam collapses where the water body itself changes
    dramatically and would corrupt a water-based calibration.
    Falls back to any non-water land if urban coverage is insufficient.
    """
    lr_vh = _logratio(context["vh_slv"], context["vh_mst"],
                      context["nd_vs"], context["nd_vm"])
    lr_vv = _logratio(context["vv_slv"], context["vv_mst"],
                      context["nd_ss"], context["nd_sm"])

    urban = context["lc"] == urban_class
    u_vh = lr_vh[urban & np.isfinite(lr_vh)]
    u_vv = lr_vv[urban & np.isfinite(lr_vv)]

    if u_vh.size >= 50:
        offset_vh = float(np.median(u_vh))
        offset_vv = float(np.median(u_vv))
        print(f"|\tScene offsets (urban ref): VH={offset_vh:+.2f} dB, "
              f"VV={offset_vv:+.2f} dB ({u_vh.size} pixels)")
        return offset_vh, offset_vv

    # Fallback: any stable non-water land pixel
    print(f"|\t[WARN] Only {u_vh.size} urban pixels — falling back to non-water land.")
    non_water = context["lc"] != water_class
    nw_vh = lr_vh[non_water & np.isfinite(lr_vh)]
    nw_vv = lr_vv[non_water & np.isfinite(lr_vv)]

    if nw_vh.size >= 50:
        offset_vh = float(np.median(nw_vh))
        offset_vv = float(np.median(nw_vv))
        print(f"|\tScene offsets (non-water ref): VH={offset_vh:+.2f} dB, "
              f"VV={offset_vv:+.2f} dB ({nw_vh.size} pixels)")
        return offset_vh, offset_vv

    print("|\t[WARN] Insufficient reference pixels — offsets set to 0.")
    return 0.0, 0.0


def compute_adaptive_thresholds(context: dict[str, Any], offset_vh: float, offset_vv: float,
                                n_sigma: float = 2.5) -> dict[str, tuple[float, float]]:
    """Compute scene-adaptive local change flags using urban context distributions as noise filters."""
    lr_vh = _logratio(context["vh_slv"], context["vh_mst"], context["nd_vs"], context["nd_vm"]) - offset_vh
    lr_vv = _logratio(context["vv_slv"], context["vv_mst"], context["nd_ss"], context["nd_sm"]) - offset_vv

    urban = context["lc"] == 50
    u_vh = lr_vh[urban & np.isfinite(lr_vh)]
    u_vv = lr_vv[urban & np.isfinite(lr_vv)]

    n_sigma = float(np.clip(n_sigma, 2.0, 3.5))

    if u_vh.size < 200:
        print(f"|\t[WARN] Only {u_vh.size} urban reference points found — falling back to fixed baselines.")
        return {"open": (-3.5, -3.0), "forest": (-4.0, -3.5), "urban_dec": (-5.0, -5.0)}

    mean_vh, std_vh = float(np.median(u_vh)), float(np.std(u_vh))
    mean_vv, std_vv = float(np.median(u_vv)), float(np.std(u_vv))

    thr_vh = np.clip(mean_vh - n_sigma * std_vh, -5.2, -3.5)
    thr_vv = np.clip(mean_vv - n_sigma * std_vv, -4.7, -3.0)

    # Secondary structural adjustments for canopy and built-up environments
    thr_forest_vh = np.clip(thr_vh - 0.5, -6.0, -4.0)
    thr_forest_vv = np.clip(thr_vv - 0.5, -6.0, -3.5)
    thr_urban_vh  = np.clip(thr_vh + 0.5, -4.5, -3.5)
    thr_urban_vv  = np.clip(thr_vv + 0.5, -4.0, -3.0)

    print(f"|\tAdaptive structural flags (Open): VH < {thr_vh:.2f} dB, VV < {thr_vv:.2f} dB")
    print(f"|\tForest Canopy: VH < {thr_forest_vh:.2f}, VV < {thr_forest_vv:.2f}")
    print(f"|\tHigh Density Urban: VH < {thr_urban_vh:.2f}, VV < {thr_urban_vv:.2f}")

    return {
        "open": (thr_vh, thr_vv),
        "forest": (thr_forest_vh, thr_forest_vv),
        "urban_dec": (thr_urban_vh, thr_urban_vv),
    }


# ── TOPOGRAPHIC PROCESSING ──────────────────────────────────────────────────

def compute_elevation_ceiling(data_folder: Path, elev_name: str, lc_name: str, out_tif: Path,
                              water_class: int = 80, surge_buffer_m: float = 8.0) -> Path:
    """Calculate hydro-correct continuous maximum terrain bounds over regional water boundaries."""
    elev_path = data_folder / elev_name if elev_name.endswith('.img') else data_folder / f"{elev_name}.img"
    lc_path = data_folder / lc_name if lc_name.endswith('.img') else data_folder / f"{lc_name}.img"

    with rasterio.open(elev_path) as src_eff:
        elev = src_eff.read(1)
        crs = src_eff.crs
        transform = src_eff.transform
        
    with rasterio.open(lc_path) as src_lc:
        lc = src_lc.read(1)

    h, w = elev.shape
    fallback = float(np.nanmin(elev))
    water_mask = (lc == water_class) & (elev > -50)
    
    # Stratified 10px downsampling step pattern to scale execution speed
    step = 10
    y_indices, x_indices = np.where(water_mask[::step, ::step])
    y_points = y_indices * step
    x_points = x_indices * step
    vals = elev[y_points, x_points]
    
    if len(vals) >= 10:
        grid_y, grid_x = np.mgrid[0:h, 0:w]
        surface = griddata((y_points, x_points), vals, (grid_y, grid_x), method="nearest")
    else:
        surface = np.full((h, w), fallback, dtype=np.float32)
        
    surface = gaussian_filter((surface + surge_buffer_m).astype(np.float32), sigma=40)
    
    meta = {
        'driver': 'GTiff', 'dtype': rasterio.float32, 'nodata': -9999.0,
        'width': w, 'height': h, 'count': 1, 'crs': crs, 'transform': transform
    }
    
    out_tif.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out_tif, "w", **meta) as dst:
        dst.write(surface, 1)
        
    return out_tif


# ── POST-PROCESSING & ANALYTICS ─────────────────────────────────────────────

def build_snap_expressions(bands: dict, offset_vh: float, offset_vv: float, thresholds: dict) -> dict[str, str]:
    """Compile optimized math nodes mapping directly into the SNAP processing engine specs."""
    f = "4.342944819"  # Constant representing 10 / ln(10)
    vh_slv, vh_mst = bands["vh_slv"], bands["vh_mst"]
    vv_slv, vv_mst = bands["vv_slv"], bands["vv_mst"]

    o_vh, o_vv   = thresholds["open"]
    f_vh, f_vv   = thresholds["forest"]
    ud_vh, ud_vv = thresholds["urban_dec"]

    return {
        "vh_norm": f"({f} * log({vh_slv} / {vh_mst}) - ({offset_vh:.4f}))",
        "vv_norm": f"({f} * log({vv_slv} / {vv_mst}) - ({offset_vv:.4f}))",
        "has_data": f"(!nan({vh_slv}) AND !nan({vh_mst}) AND !nan({vv_slv}) AND !nan({vv_mst}))",
        "thr_open_vh": f"{o_vh:.4f}", "thr_open_vv": f"{o_vv:.4f}",
        "thr_forest_vh": f"{f_vh:.4f}", "thr_forest_vv": f"{f_vv:.4f}",
        "thr_urban_vh": f"{ud_vh:.4f}", "thr_urban_vv": f"{ud_vv:.4f}",
    }


def export_clean_tif(flood_dim: Path, out_tif: Path, min_blob_px: int = 500) -> None:
    """Extract clean classified change arrays masking small-scale noise artifacts."""
    data_folder = Path(str(flood_dim).replace(".dim", ".data"))
    imgs = list(data_folder.glob("Flood*.img"))
    if not imgs:
        raise FileNotFoundError(f"No operational Flood bands located in path: {data_folder}")

    with rasterio.open(imgs[0]) as src:
        raw = src.read(1)
        meta = src.meta.copy()

    flood = np.isfinite(raw) & (raw == 1)

    # Clean topological features through binary mathematical morphology
    clean = ndimage.binary_opening(flood, structure=np.ones((5, 5), dtype=bool))
    clean = ndimage.binary_closing(clean, structure=np.ones((3, 3), dtype=bool))

    labeled, n = label(clean) # type: ignore
    if int(n) > 0:
        sizes = ndimage.sum(clean, labeled, range(1, int(n) + 1))
        remove = np.where(np.array(sizes) < min_blob_px)[0] + 1
        clean[np.isin(labeled, remove)] = False

    out = np.where(clean, 255, 0).astype(np.uint8)

    meta.update(driver="GTiff", dtype=rasterio.uint8, count=1,
                compress="deflate", tiled=True, blockxsize=512, blockysize=512, nodata=0)
                
    with rasterio.open(out_tif, "w", **meta) as dst:
        dst.write(out, 1)

    print(f"|\tFlood mask exported successfully: {out_tif}")
    print(f"|\tTotal flooded pixels detected: {int(clean.sum()):,}")


def computeFloodArea(data: ProductData) -> tuple[int, float, float]:
    """Compute active flood pixel quantities, unit surface spaces, and final area footprints."""
    flood_mask = (~data.band.mask) & (data.band.data == 1)
    clean_mask = ndimage.binary_opening(flood_mask, structure=np.ones((3, 3)))
    flood_count = int(np.count_nonzero(clean_mask))

    if data.crs and data.crs.is_geographic:
        res_x, res_y = _get_geographic_pixel_area(data.transform, data.height, data.width)
        px_area_m2 = res_x * res_y
    else:
        px_area_m2 = abs(data.transform.a * data.transform.e)

    return flood_count, px_area_m2, flood_count * px_area_m2