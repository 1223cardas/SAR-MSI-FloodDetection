from pathlib import Path
import numpy as np
import rasterio
from rasterio.windows import Window
from scipy import ndimage
from scipy.ndimage import gaussian_filter, label
from scipy.interpolate import griddata


# ── helpers ────────────────────────────────────────────────────────────────

def _read_band(data_folder: Path, keyword: str) -> tuple[np.ndarray, dict, object]:
    """Find the .img file whose name contains keyword and return (array, meta, nodata)."""
    matches = list(data_folder.glob(f"*{keyword}*.img"))
    if not matches:
        raise FileNotFoundError(f"No band matching '{keyword}' in {data_folder}")
    with rasterio.open(matches[0]) as ds:
        return ds.read(1).astype(np.float32), ds.meta.copy(), ds.nodata


def _logratio(slv: np.ndarray, mst: np.ndarray,
               slv_nd=None, mst_nd=None) -> np.ndarray:
    """10 * log10(slave / master) in dB. Invalid pixels → NaN."""
    valid = (slv > 0) & (mst > 0) & np.isfinite(slv) & np.isfinite(mst)
    if slv_nd is not None:
        valid &= slv != slv_nd
    if mst_nd is not None:
        valid &= mst != mst_nd
    out = np.full(slv.shape, np.nan, dtype=np.float32)
    out[valid] = 10.0 * np.log10(slv[valid] / mst[valid])
    return out


# ── scene normalization ─────────────────────────────────────────────────────

def compute_scene_offsets(data_folder: Path,
                          vh_slv_name: str, vh_mst_name: str,
                          vv_slv_name: str, vv_mst_name: str,
                          lc_name: str,
                          water_class: int = 80) -> tuple[float, float]:
    """
    Compute per-scene log-ratio offset from permanent water pixels (class 80).

    Permanent water should be radiometrically stable between passes, so its
    median log-ratio should be ≈ 0 dB. Any deviation is a scene-level bias
    (atmospheric path delay difference, residual thermal noise, wind roughening).
    Subtracting this offset from all pixels puts the scene in a common reference
    frame where absolute thresholds are physically meaningful.

    Returns (offset_vh_db, offset_vv_db).
    """
    vh_slv, _, nd_vs = _read_band(data_folder, vh_slv_name)
    vh_mst, _, nd_vm = _read_band(data_folder, vh_mst_name)
    vv_slv, _, nd_ss = _read_band(data_folder, vv_slv_name)
    vv_mst, _, nd_sm = _read_band(data_folder, vv_mst_name)
    lc, _, _         = _read_band(data_folder, lc_name)

    water = lc == water_class
    lr_vh = _logratio(vh_slv, vh_mst, nd_vs, nd_vm)
    lr_vv = _logratio(vv_slv, vv_mst, nd_ss, nd_sm)

    w_vh = lr_vh[water & np.isfinite(lr_vh)]
    w_vv = lr_vv[water & np.isfinite(lr_vv)]

    if w_vh.size < 50:
        print(f"|\t[WARN] Only {w_vh.size} water pixels — offset correction skipped.")
        return 0.0, 0.0

    offset_vh = float(np.median(w_vh))
    offset_vv = float(np.median(w_vv))
    print(f"|\tScene offsets: VH={offset_vh:+.2f} dB, VV={offset_vv:+.2f} dB "
          f"({w_vh.size} water pixels)")
    return offset_vh, offset_vv


# ── elevation ceiling ───────────────────────────────────────────────────────

def compute_elevation_ceiling(data_folder: Path,
                               elev_name: str, lc_name: str,
                               out_tif: Path,
                               water_class: int = 80,
                               tile_size: int = 512) -> Path:
    """
    Spatially adaptive elevation ceiling from permanent water pixels.
    P95 elevation per tile → interpolated smooth surface.
    Pixels above this surface are unlikely to be flooded.
    """
    if out_tif.exists():
        return out_tif

    elev, meta, nd = _read_band(data_folder, elev_name)
    lc, _, _       = _read_band(data_folder, lc_name)
    h, w = elev.shape
    valid = np.isfinite(elev)
    if nd is not None:
        valid &= elev != nd

    cy, cx, vals = [], [], []
    for r in range(0, h, tile_size):
        for c in range(0, w, tile_size):
            th = min(tile_size, h - r)
            tw = min(tile_size, w - c)
            e_tile = elev[r:r+th, c:c+tw]
            lc_tile = lc[r:r+th, c:c+tw]
            v_tile = valid[r:r+th, c:c+tw]
            water_elev = e_tile[(lc_tile == water_class) & v_tile]
            if water_elev.size < 10:
                continue
            vals.append(float(np.percentile(water_elev, 95)))
            cy.append(r + th / 2)
            cx.append(c + tw / 2)

    if not vals:
        raise RuntimeError("No water pixels — cannot compute elevation ceiling.")

    grid_y, grid_x = np.mgrid[0:h, 0:w]
    points = np.column_stack([cy, cx])
    fallback = float(np.median(vals))
    if len(vals) >= 4:
        surface = griddata(points, vals, (grid_y, grid_x),
                           method="linear", fill_value=fallback)
    else:
        surface = np.full((h, w), fallback, dtype=np.float32)
    surface = gaussian_filter(surface.astype(np.float32), sigma=3.0)

    meta = meta.copy()
    meta.update(driver="GTiff", dtype=rasterio.float32, count=1,
                compress="deflate", tiled=True, blockxsize=512, blockysize=512)
    with rasterio.open(out_tif, "w", **meta) as dst:
        dst.write(surface, 1)
    print(f"|\tElevation ceiling written ({len(vals)} tiles, "
          f"range [{min(vals):.1f}–{max(vals):.1f}] m)")
    return out_tif


# ── slope mask ──────────────────────────────────────────────────────────────

def compute_slope_mask(data_folder: Path, elev_name: str,
                       out_tif: Path, max_slope_deg: float = 15.0) -> Path:
    """Binary slope mask: 1 where slope < max_slope_deg, 0 elsewhere."""
    if out_tif.exists():
        return out_tif

    import math
    elev, meta, nd = _read_band(data_folder, elev_name)
    if nd is not None:
        elev[elev == nd] = np.nan

    res_x = abs(meta["transform"].a)
    res_y = abs(meta["transform"].e)
    if meta.get("crs") and rasterio.crs.CRS.from_dict(meta["crs"]).is_geographic:
        lat = (meta["transform"].f + meta["transform"].e * elev.shape[0] / 2)
        lat_rad = math.radians(lat)
        R = 6378137.0
        res_x = res_x * math.pi / 180.0 * R * math.cos(lat_rad)
        res_y = res_y * math.pi / 180.0 * R

    slope_deg = np.degrees(np.arctan(np.sqrt(
        np.gradient(elev, res_x, axis=1) ** 2 +
        np.gradient(elev, res_y, axis=0) ** 2
    )))
    mask = np.where(np.isfinite(slope_deg) & (slope_deg < max_slope_deg),
                    1, 0).astype(np.uint8)

    meta = meta.copy()
    meta.update(driver="GTiff", dtype=rasterio.uint8, count=1,
                compress="deflate", tiled=True, blockxsize=512, blockysize=512,
                nodata=None)
    with rasterio.open(out_tif, "w", **meta) as dst:
        dst.write(mask, 1)
    print(f"|\tSlope mask written (threshold: {max_slope_deg}°)")
    return out_tif


# ── SNAP expression builder ─────────────────────────────────────────────────

def build_snap_expressions(bands: dict, offset_vh: float, offset_vv: float,
                            thresholds: dict) -> dict[str, str]:
    f = "4.342944819"
    vh_slv, vh_mst = bands["vh_slv"], bands["vh_mst"]
    vv_slv, vv_mst = bands["vv_slv"], bands["vv_mst"]

    vh_norm = f"({f} * log({vh_slv} / {vh_mst}) - ({offset_vh:.4f}))"
    vv_norm = f"({f} * log({vv_slv} / {vv_mst}) - ({offset_vv:.4f}))"
    has_data = (f"({vh_slv} > 0 AND {vh_mst} > 0"
                f" AND {vv_slv} > 0 AND {vv_mst} > 0)")

    # Bake thresholds directly into the expressions as constants
    o_vh, o_vv   = thresholds["open"]
    f_vh, f_vv   = thresholds["forest"]
    ud_vh, ud_vv = thresholds["urban_dec"]

    return {
        "vh_norm":        vh_norm,
        "vv_norm":        vv_norm,
        "has_data":       has_data,
        "thr_open_vh":    f"{o_vh:.4f}",
        "thr_open_vv":    f"{o_vv:.4f}",
        "thr_forest_vh":  f"{f_vh:.4f}",
        "thr_forest_vv":  f"{f_vv:.4f}",
        "thr_urban_vh":   f"{ud_vh:.4f}",
        "thr_urban_vv":   f"{ud_vv:.4f}",
    }


def compute_adaptive_thresholds(
    data_folder: Path,
    vh_slv_name: str, vh_mst_name: str,
    vv_slv_name: str, vv_mst_name: str,
    lc_name: str,
    offset_vh: float, offset_vv: float,
    n_sigma: float = 2.5,
) -> dict[str, float]:
    """
    Compute scene-adaptive flood thresholds using urban pixels (class 50)
    as a stability reference.

    Urban areas are radiometrically stable between passes (buildings don't
    disappear), so their normalized log-ratio distribution represents the
    scene noise floor — the expected magnitude of change WITHOUT flooding.

    threshold = mean(urban) - n_sigma * std(urban)

    For a 6-day baseline this typically gives ~ -3 to -4 dB.
    For a 12-day baseline this automatically tightens to ~ -5 to -7 dB,
    preventing the agricultural false positives seen in Valencia.

    n_sigma=2.5 rejects ~99% of stable urban pixels as non-flood.
    """
    vh_slv, _, nd_vs = _read_band(data_folder, vh_slv_name)
    vh_mst, _, nd_vm = _read_band(data_folder, vh_mst_name)
    vv_slv, _, nd_ss = _read_band(data_folder, vv_slv_name)
    vv_mst, _, nd_sm = _read_band(data_folder, vv_mst_name)
    lc, _, _         = _read_band(data_folder, lc_name)

    lr_vh = _logratio(vh_slv, vh_mst, nd_vs, nd_vm) - offset_vh
    lr_vv = _logratio(vv_slv, vv_mst, nd_ss, nd_sm) - offset_vv

    urban = lc == 50
    u_vh = lr_vh[urban & np.isfinite(lr_vh)]
    u_vv = lr_vv[urban & np.isfinite(lr_vv)]

    # Clamp n_sigma between 2.0 and 3.5 — prevents thresholds becoming
    # either too permissive (< 2.0) or impossibly strict (> 3.5)
    n_sigma = float(np.clip(n_sigma, 2.0, 3.5))

    if u_vh.size < 200:
        print(f"|\t[WARN] Only {u_vh.size} urban pixels — using fixed thresholds.")
        return {"open": (-3.5, -3.0), "forest": (-4.0, -3.5), "urban_dec": (-5.0, -5.0)}

    mean_vh, std_vh = float(np.median(u_vh)), float(np.std(u_vh))
    mean_vv, std_vv = float(np.median(u_vv)), float(np.std(u_vv))

    # Floor: never go above -3.5 dB even on very stable short-baseline scenes
    thr_vh = np.clip(mean_vh - n_sigma * std_vh, -6.0, -3.5)
    thr_vv = np.clip(mean_vv - n_sigma * std_vv, -6.0, -3.0)

    # Forest and urban submersion need stricter thresholds
    thr_forest_vh = np.clip(thr_vh - 0.5, -6.5, -4.0)
    thr_forest_vv = np.clip(thr_vv - 0.5, -6.5, -3.5)
    thr_urban_vh  = np.clip(thr_vh - 1.5, -7.0, -5.0)
    thr_urban_vv  = np.clip(thr_vv - 1.5, -7.0, -5.0)

    print(f"|\tAdaptive thresholds (open land): VH < {thr_vh:.2f} dB, VV < {thr_vv:.2f} dB")
    print(f"|\tForest: VH < {thr_forest_vh:.2f}, VV < {thr_forest_vv:.2f}")
    print(f"|\tUrban submersion: VH < {thr_urban_vh:.2f}, VV < {thr_urban_vv:.2f}")

    return {
        "open":      (thr_vh, thr_vv),
        "forest":    (thr_forest_vh, thr_forest_vv),
        "urban_dec": (thr_urban_vh, thr_urban_vv),
    }



# ── post-processing ─────────────────────────────────────────────────────────

def export_clean_tif(flood_dim: Path, out_tif: Path,
                     min_blob_px: int = 500) -> None:
    """
    Export the Flood band from SNAP .dim → cleaned uint8 GeoTIFF.

    Encoding:  0 = dry (valid scene area)
               1 = flood detected
             255 = outside scene / nodata
    """
    data_folder = Path(str(flood_dim).replace(".dim", ".data"))
    imgs = list(data_folder.glob("Flood*.img"))
    if not imgs:
        raise FileNotFoundError(f"No Flood band in {data_folder}")

    with rasterio.open(imgs[0]) as src:
        raw  = src.read(1)
        meta = src.meta.copy()

    valid = np.isfinite(raw)
    flood = valid & (raw == 1)

    # 5×5 binary opening removes isolated speckle lines and dots
    clean = ndimage.binary_opening(flood, structure=np.ones((5, 5)))

    # Morphological closing to fill small holes inside flood regions
    clean = ndimage.binary_closing(clean, structure=np.ones((3, 3)))

    # Remove blobs smaller than min_blob_px (typically < 0.5 ha at 10 m)
    labeled, n = label(clean)
    if n > 0:
        sizes = ndimage.sum(clean, labeled, range(1, n + 1))
        remove = np.where(np.array(sizes) < min_blob_px)[0] + 1
        clean[np.isin(labeled, remove)] = False

    out = np.full(raw.shape, 255, dtype=np.uint8)  # nodata everywhere
    out[valid] = 0                                   # valid area = dry
    out[clean] = 1                                   # detected flood

    meta.update(driver="GTiff", dtype=rasterio.uint8, count=1,
                compress="deflate", tiled=True,
                blockxsize=512, blockysize=512, nodata=255)
    with rasterio.open(out_tif, "w", **meta) as dst:
        dst.write(out, 1)
    print(f"|\tFlood mask exported: {out_tif}")
    n_flood = int(clean.sum())
    print(f"|\tFlooded pixels: {n_flood:,}")