from pathlib import Path
import numpy as np
import rasterio
import math
from scipy.ndimage import gaussian_filter, label
from rasterio.transform import array_bounds
from scipy.interpolate import griddata
from rasterio.crs import CRS
from scipy import ndimage

from .pclasses import ProductData

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
                               surge_buffer_m: float = 8.0) -> Path:

    elev_path = data_folder / elev_name
    if not elev_path.exists() and not elev_name.endswith('.img'):
        elev_path = data_folder / f"{elev_name}.img"

    lc_path = data_folder / lc_name
    if not lc_path.exists() and not lc_name.endswith('.img'):
        lc_path = data_folder / f"{lc_name}.img"
        
    # Abrir e extrair apenas a matriz e a georreferenciação
    with rasterio.open(elev_path) as src_eff:
        elev = src_eff.read(1)
        crs = src_eff.crs
        transform = src_eff.transform
        
    with rasterio.open(lc_path) as src_lc:
        lc = src_lc.read(1)
        
    h, w = elev.shape
    fallback = float(np.nanmin(elev))
    
    # Isolar onde existe água permanente
    water_mask = (lc == water_class) & (elev > -50)
    
    # Amostrar a imagem uniformemente (a cada 10 píxeis)
    step = 10
    y_indices, x_indices = np.where(water_mask[::step, ::step])
    y_points = y_indices * step
    x_points = x_indices * step
    
    vals = elev[y_points, x_points]
    
    if len(vals) >= 10:
        grid_y, grid_x = np.mgrid[0:h, 0:w]
        # Interpolação global contínua
        surface = griddata((y_points, x_points), vals, (grid_y, grid_x),
                           method="nearest")
    else:
        surface = np.full((h, w), fallback, dtype=np.float32)
        
    # Aplicar o buffer de cheia e suavizar a matriz completa
    surface = surface + surge_buffer_m
    surface = gaussian_filter(surface.astype(np.float32), sigma=40)
    
    meta = {
        'driver': 'GTiff',
        'dtype': rasterio.float32,
        'nodata': np.nan,
        'width': w,
        'height': h,
        'count': 1,
        'crs': crs,
        'transform': transform
    }
    
    # Gravar o GeoTIFF real e padronizado
    with rasterio.open(out_tif, "w", **meta) as dst:
        dst.write(surface, 1)
        
    return out_tif


# ── slope mask ──────────────────────────────────────────────────────────────

def compute_slope_mask(data_folder: Path, elev_name: str,
                       out_tif: Path, max_slope_deg: float = 15.0) -> Path:
    """Binary slope mask: 1 where slope < max_slope_deg, 0 elsewhere."""
    if out_tif.exists():
        return out_tif

    elev, meta, nd = _read_band(data_folder, elev_name)
    if nd is not None:
        elev[elev == nd] = np.nan

    res_x = abs(meta["transform"].a)
    res_y = abs(meta["transform"].e)
    if meta.get("crs") and CRS.from_dict(meta["crs"]).is_geographic:
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
) -> dict[str, tuple[float, float]]:
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

    # Floor: impede que os limiares se tornem um abismo intransponível
    thr_vh = np.clip(mean_vh - n_sigma * std_vh, -5.2, -3.5)
    thr_vv = np.clip(mean_vv - n_sigma * std_vv, -4.7, -3.0)

    # Forest and urban submersion need stricter thresholds
    thr_forest_vh = np.clip(thr_vh - 0.5, -6.0, -4.0)
    thr_forest_vv = np.clip(thr_vv - 0.5, -6.0, -3.5)

    thr_urban_vh  = np.clip(thr_vh + 0.5, -4.5, -3.5)
    thr_urban_vv  = np.clip(thr_vv + 0.5, -4.0, -3.0)

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
    Exporta apenas a máscara de inundação (Branco = 255).
    O resto da imagem é classificado como NoData (Transparente = 0).
    """
    data_folder = Path(str(flood_dim).replace(".dim", ".data"))
    imgs = list(data_folder.glob("Flood*.img"))
    if not imgs:
        raise FileNotFoundError(f"No Flood band in {data_folder}")

    with rasterio.open(imgs[0]) as src:
        raw: np.ndarray = src.read(1)
        meta = src.meta.copy()

    valid = np.isfinite(raw)
    flood = valid & (raw == 1)

    # Filtragem morfológica
    clean = ndimage.binary_opening(flood, structure=np.ones((5, 5), dtype=bool))
    clean = ndimage.binary_closing(clean, structure=np.ones((3, 3), dtype=bool))

    # Remoção de pequenos blocos (ruído)
    labeled, n = label(clean)  # type: ignore
    if int(n) > 0:
        sizes = ndimage.sum(clean, labeled, range(1, int(n) + 1))
        remove = np.where(np.array(sizes) < min_blob_px)[0] + 1
        clean[np.isin(labeled, remove)] = False

    # Começa tudo a 0 (que será definido como NoData)
    out = np.full(raw.shape, 0, dtype=np.uint8)   
    
    # Onde for inundação, passa a 255 (Branco)
    clean = np.asarray(clean, dtype=bool)
    out[clean] = 255 

    # Atualiza os metadados definindo explicitamente o 0 como NODATA
    meta.update(driver="GTiff", dtype=rasterio.uint8, count=1,
                compress="deflate", tiled=True,
                blockxsize=512, blockysize=512, nodata=0) # <--- Muito importante
                
    with rasterio.open(out_tif, "w", **meta) as dst:
        dst.write(out, 1)

    print(f"|\tFlood mask exported: {out_tif}")
    n_flood = int(clean.sum())
    print(f"|\tFlooded pixels: {n_flood:,}")


# ── FloodArea ─────────────────────────────────────────────────────────

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