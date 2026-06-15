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
from skimage.filters import threshold_otsu
from .pclasses import ProductData
from .utils import get_band_file
from .paths import build_cache_file

def isValidMask(arr: np.ndarray, nodata=None) -> np.ndarray:
    mask = np.isfinite(arr)

    if nodata is not None:
        mask &= arr != nodata

    return mask


def updateGtiffMeta(meta: dict, dtype) -> dict:
    meta = meta.copy()

    meta.update(
        driver="GTiff",
        dtype=dtype,
        count=1,
        compress="deflate",
        tiled=True,
        blockxsize=512,
        blockysize=512,
    )

    return meta


def iterateTiles(
    height: int,
    width: int,
    tile_size: int,
) -> Iterator[tuple[int, int, int, int]]:
    for row in range(0, height, tile_size):
        for col in range(0, width, tile_size):
            yield (
                row,
                col,
                min(tile_size, height - row),
                min(tile_size, width - col),
            )


def interpolateSurface(
    height: int,
    width: int,
    points: np.ndarray,
    values: list[float],
    sigma: float = 3.0,
    method: str = "linear",
) -> np.ndarray:
    grid_y, grid_x = np.mgrid[0:height, 0:width]

    fallback = float(np.min(values))

    if len(values) >= 4:
        surface = griddata(
            points,
            values,
            (grid_y, grid_x),
            method=method,
            fill_value=fallback,
        )
    else:
        surface = np.full(
            (height, width),
            fallback,
            dtype=np.float32,
        )

    return gaussian_filter(
        surface.astype(np.float32),
        sigma=sigma,
    )


def geographic_resolution_to_meters(
    transform,
    latitude_deg: float,
) -> tuple[float, float]:
    earth_radius = 6378137.0

    lat_rad = math.radians(latitude_deg)

    meters_per_deg_lat = (
        math.pi / 180.0
    ) * earth_radius

    meters_per_deg_lon = (
        math.pi / 180.0
    ) * earth_radius * math.cos(lat_rad)

    return (
        abs(transform.a) * meters_per_deg_lon,
        abs(transform.e) * meters_per_deg_lat,
    )



def compute_water_elevation_p95(
    data_file: Path,
    vars: list[str],
    water_class: int = 80,
    tile_size: int = 512,
    margin_m: float = 0.0,
) -> Path:
    elev_band_name, lc_band_name = vars
 
    if lc_band_name == "":
        raise RuntimeError("No land cover band found in stack product.")
    if elev_band_name == "":
        raise RuntimeError("No elevation band found in stack product.")
 
    with rasterio.open(get_band_file(data_file, elev_band_name)) as elev_ds:
        elevation = elev_ds.read(1).astype(np.float32)
        elev_nodata = elev_ds.nodata
        meta = elev_ds.meta.copy()
        h, w = elev_ds.height, elev_ds.width
 
    with rasterio.open(get_band_file(data_file, lc_band_name)) as lc_ds:
        landcover = lc_ds.read(1)
 
    valid_elev = isValidMask(elevation, elev_nodata)
 
    tile_centers_x, tile_centers_y, tile_thresholds = [], [], []

    # n_rows = math.ceil(h / tile_size) #
    # n_cols = math.ceil(w / tile_size) #
    # debug_grid = np.full(
    #     (n_rows, n_cols),
    #     np.nan,
    #     dtype=np.float32
    # ) #dbg
    
    for row, col, win_h, win_w in iterateTiles(h, w, tile_size):
        #get tiles for elevation, landcover and the valid tile
        elev_tile = elevation[row:row + win_h, col:col + win_w]
        landCover_tile = landcover[row:row + win_h, col:col + win_w]
        valid_tile = valid_elev[row:row + win_h, col:col + win_w]

        #get water elevation in the tile
        water_mask = (landCover_tile == water_class) & valid_tile
        water_elev = elev_tile[water_mask]

        if water_elev.size < 10:
            continue  # not enough water pixels — interpolate later

        # tile_row = row // tile_size #dbg
        # tile_col = col // tile_size #dbg

        threshold = float(np.percentile(water_elev, 95)) + margin_m
        
        # debug_grid[tile_row, tile_col] = threshold #dbg

        tile_centers_y.append(row + win_h / 2)
        tile_centers_x.append(col + win_w / 2)
        tile_thresholds.append(threshold)


    if not tile_thresholds:
        raise RuntimeError("No water pixels found in any tile — cannot compute elevation threshold.")
    
    # print("\n=== TILE THRESHOLDS ===")
    # with np.printoptions(
    #     precision=1,
    #     suppress=True,
    #     linewidth=300
    # ): print(debug_grid)

    print(
        f"|\tElevation threshold surface: {len(tile_thresholds)} tiles with water pixels, "
        f"range [{min(tile_thresholds):.1f}, {max(tile_thresholds):.1f}] m"
    )

    # --- Interpolate tile values to a full raster ---
    points = np.column_stack([tile_centers_y, tile_centers_x])
    surface = interpolateSurface(h, w, points, tile_thresholds)

    out_path = build_cache_file("elev_threshold.tif")

    if not out_path.exists():
        meta = updateGtiffMeta(meta, rasterio.float32)

        with rasterio.open(out_path, "w", **meta) as dst:
            dst.write(surface.astype(np.float32), 1)

    return out_path

    # grid_y, grid_x = np.mgrid[0:h, 0:w]
    # points = np.column_stack([tile_centers_y, tile_centers_x])
 
    # if len(tile_thresholds) >= 4:
    #     surface = griddata(points, tile_thresholds, (grid_y, grid_x),
    #                        method='linear', fill_value=float(np.min(tile_thresholds)))
    # else:
    #     # Too few control points for interpolation — use global max as safe fallback
    #     surface = np.full((h, w), float(np.max(tile_thresholds)), dtype=np.float32)
 
    # surface = gaussian_filter(surface.astype(np.float32), sigma=3.0)
 
    # out_path = elev_img.parent.parent / 'elev_threshold.tif'
    # if not out_path.exists():
    #     meta.update(driver='GTiff', dtype=rasterio.float32, count=1,
    #                 compress='deflate', tiled=True, blockxsize=512, blockysize=512)
    #     with rasterio.open(str(out_path), 'w', **meta) as dst:
    #         dst.write(surface.astype(np.float32), 1)

    # return out_path



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
    clean_flood_mask = ndimage.binary_opening(flood_mask, structure=np.ones((3,3)))
    flood_count = int(np.count_nonzero(clean_flood_mask))

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


def compute_slope_mask_tif(elev_img: Path, out_tif: Path, max_slope_deg: float = 15.0) -> None:
    """
    Compute a binary slope mask from a DEM band and write it as a GTiff.
    Pixels where slope < max_slope_deg → 1 (keep), steeper → 0 (exclude).
    """
    with rasterio.open(elev_img) as src:
        elev = src.read(1).astype(np.float32)
        res_x = abs(src.transform.a)  # pixel width in CRS units
        res_y = abs(src.transform.e)  # pixel height in CRS units
        meta = src.meta.copy()
        nodata = src.nodata

        if src.crs and src.crs.is_geographic:
            centre_lat = (src.bounds.bottom + src.bounds.top) / 2.0
            res_x, res_y = geographic_resolution_to_meters(src.transform, centre_lat)

    elev[~isValidMask(elev, nodata)] = np.nan

    dz_dx = np.gradient(elev, res_x, axis=1)
    dz_dy = np.gradient(elev, res_y, axis=0)

    slope_rad = np.arctan(np.sqrt(dz_dx**2 + dz_dy**2))
    slope_deg = np.degrees(slope_rad)

    mask = np.where(np.isfinite(slope_deg) & (slope_deg < max_slope_deg), 1, 0).astype(np.uint8)

    meta = updateGtiffMeta(meta, rasterio.uint8)
    meta["nodata"] = None

    with rasterio.open(out_tif, "w", **meta) as dst:
        dst.write(mask, 1)

    print(f"|\tSlope mask written to {out_tif} (threshold: {max_slope_deg}°)")


# def export_diff_tif(data_folder: Path, slv_mst: list[str], out_tif: Path) -> None:
#     """
#     Write a log-ratio diff raster to a GeoTIFF.
#     Streamed in 512-row blocks to avoid loading full rasters into memory.
#     """
#     slv, mst = slv_mst
#     slv_img = get_band_file(data_folder, slv)
#     mst_img = get_band_file(data_folder, mst)

#     with rasterio.open(slv_img) as slv_ds, rasterio.open(mst_img) as mst_ds:
#         if slv_ds.shape != mst_ds.shape:
#             raise ValueError(
#                 f"Slave/master shapes do not match for diff export: "
#                 f"{slv_ds.shape} vs {mst_ds.shape}"
#             )
#         meta = slv_ds.meta.copy()
#         meta.update(driver="GTiff", dtype=rasterio.float32, count=1,
#                     compress="deflate", tiled=True, blockxsize=512, blockysize=512)

#         with rasterio.open(out_tif, "w", **meta) as dst:
#             h, w = slv_ds.height, slv_ds.width
#             for row in range(0, h, 512):
#                 window = Window(0, row, w, min(512, h - row))
#                 slv = slv_ds.read(1, window=window).astype(np.float32)
#                 mst = mst_ds.read(1, window=window).astype(np.float32)

#                 valid = (slv > 0) & (mst > 0) & np.isfinite(slv) & np.isfinite(mst)
#                 if slv_ds.nodata is not None:
#                     valid &= slv != slv_ds.nodata
#                 if mst_ds.nodata is not None:
#                     valid &= mst != mst_ds.nodata

#                 out = np.full(slv.shape, np.nan, dtype=np.float32)
#                 if valid.any():
#                     out[valid] = (
#                         10.0 * np.log10(slv[valid]) - 10.0 * np.log10(mst[valid])
#                     )
#                 dst.write(out, 1, window=window)



def export_ndsi_tif(data_folder: Path, slv_mst: list[str], out_tif: Path) -> None:
    slv, mst = slv_mst
    slv_img = get_band_file(data_folder, slv)
    mst_img = get_band_file(data_folder, mst)

    with rasterio.open(slv_img) as slv_ds, rasterio.open(mst_img) as mst_ds:
        if slv_ds.shape != mst_ds.shape:
            raise ValueError(
                f"Slave/master shapes do not match for NDSI export: "
                f"{slv_ds.shape} vs {mst_ds.shape}"
            )
        
        meta = slv_ds.meta.copy()
        meta.update(driver="GTiff", dtype=rasterio.float32, count=1,
                    compress="deflate", tiled=True, blockxsize=512, blockysize=512)


        with rasterio.open(out_tif, "w", **meta) as dst:
            h, w = slv_ds.height, slv_ds.width
            for row in range(0, h, 512):
                window = Window(0, row, w, min(512, h - row))
                slv_arr = slv_ds.read(1, window=window).astype(np.float32)
                mst_arr = mst_ds.read(1, window=window).astype(np.float32)

                valid = (slv_arr > 0) & (mst_arr > 0) & np.isfinite(slv_arr) & np.isfinite(mst_arr)
                if slv_ds.nodata is not None:
                    valid &= slv_arr != slv_ds.nodata
                if mst_ds.nodata is not None:
                    valid &= mst_arr != mst_ds.nodata
                
                out = np.full(slv_arr.shape, np.nan, dtype=np.float32)
                if valid.any():
                    denom = slv_arr[valid] + mst_arr[valid]
                    # Guard against zero denominators (shouldn't occur with valid>0 check)
                    nonzero = denom != 0
                    idx = np.where(valid)[0][nonzero] if valid.ndim == 1 else valid
                    # Use boolean mask directly
                    safe = valid.copy()
                    safe[valid] &= (slv_arr[valid] + mst_arr[valid]) != 0
                    if safe.any():
                        out[safe] = (slv_arr[safe] - mst_arr[safe]) / (slv_arr[safe] + mst_arr[safe])
                dst.write(out, 1, window=window)

    # with rasterio.open(out_tif) as ds:
    #     arr = ds.read(1)

    # valid = np.isfinite(arr)

    # print("\n=== GLOBAL NDSI STATS ===")
    # print(f"Min:  {np.nanmin(arr):.3f}")
    # print(f"Max:  {np.nanmax(arr):.3f}")
    # print(f"Mean: {np.nanmean(arr):.3f}")
    # print(f"Std:  {np.nanstd(arr):.3f}")

    # for p in [1, 5, 10, 25, 50, 75, 90, 95, 99]:
    #     print(f"P{p}: {np.nanpercentile(arr, p):.3f}")

    # tile_size = 512

    # rows = math.ceil(h / tile_size)
    # cols = math.ceil(w / tile_size)

    # tile_matrix = np.full((rows, cols), np.nan)

    # with rasterio.open(out_tif) as ds:
    #     for row in range(rows):
    #         for col in range(cols):

    #             r0 = row * tile_size
    #             c0 = col * tile_size

    #             window = Window(
    #                 c0,
    #                 r0,
    #                 min(tile_size, w - c0),
    #                 min(tile_size, h - r0)
    #             )

    #             tile = ds.read(1, window=window)

    #             valid = np.isfinite(tile)

    #             if valid.sum() < 100:
    #                 continue

    #             tile_matrix[row, col] = np.nanmean(tile)

    # print("\n=== TILE NDSI MEAN ===")
    # print(np.round(tile_matrix, 3))


def compute_water_class_ndsi_mean(
    ndsi_tif: str,
    lc_img: str,
    water_class: int = 80,
) -> float | None:

    with rasterio.open(ndsi_tif) as diff_ds, rasterio.open(lc_img) as lc_ds:
        diff = diff_ds.read(1).astype(np.float32)
        lc = lc_ds.read(1)

    print("\n=== WATER PIXEL BACKSCATTER ===")

    with rasterio.open(lc_img) as lc_ds:
        lc = lc_ds.read(1)

    water_mask = (lc == water_class) & np.isfinite(diff)
    water_vals = diff[water_mask]

    positive = np.sum(water_vals > 0)
    negative = np.sum(water_vals < 0)
    print("positive:", positive / water_vals.size)
    print("negative:", negative / water_vals.size)
    all_water = (lc == water_class)

    print(
        "NaN fraction:",
        np.sum(all_water & ~np.isfinite(diff))
        / np.sum(all_water)
    )

    print("\n=== PERMANENT WATER DEBUG ===")
    print(f"Water class: {water_class}")
    print(f"Total pixels: {diff.size:,}")
    print(f"Water pixels: {water_vals.size:,}")

    if water_vals.size < 100:
        print(
            f"|\t[WARN] Fewer than 100 permanent water pixels found "
            f"({water_vals.size})"
        )
        return None

    print("\n=== WATER NDSI STATS ===")
    print(f"Min:  {np.min(water_vals):.3f}")
    print(f"Max:  {np.max(water_vals):.3f}")
    print(f"Mean: {np.mean(water_vals):.3f}")
    print(f"Std:  {np.std(water_vals):.3f}")

    for p in [1, 5, 10, 25, 50, 75, 90, 95, 99]:
        print(f"P{p}: {np.percentile(water_vals, p):.3f}")

    ceiling_raw = float(np.percentile(water_vals, 50)) - 0.2

    print("\n=== CEILING COMPUTATION ===")
    print(f"Median water NDSI: {np.percentile(water_vals, 50):.3f}")
    print(f"Raw ceiling:       {ceiling_raw:.3f}")

    CEILING_FLOOR = -0.3

    ceiling = ceiling_raw

    if ceiling < CEILING_FLOOR:
        print(
            f"Clamped from {ceiling:.3f} "
            f"to CEILING_FLOOR={CEILING_FLOOR:.3f}"
        )
        ceiling = CEILING_FLOOR

    print(f"Final ceiling: {ceiling:.3f}")

    return ceiling



def compute_tile_otsu_tif(
    src_band_path: Path,
    out_tif: str,
    tile_size: int = 512,
    interp_method: str = 'linear',
    interp_sigma: float = 1.5,
    min_pixels: int = 10,
    min_std: float = 0.08,
    max_threshold: float | None = -0.15,
) -> str:
    with rasterio.open(src_band_path) as src:
        meta = src.meta.copy()
        h, w = src.height, src.width
        src_nodata = src.nodata

        print(f"compute_tile_otsu_tif: src={src_band_path}, out={out_tif}, size={w}x{h}, tile={tile_size}")

        tile_centers_y, tile_centers_x, tile_thresholds = [], [], []
        total_tiles = ((h + tile_size - 1) // tile_size) * ((w + tile_size - 1) // tile_size)
        processed = 0

        for row in range(0, h, tile_size):
            for col in range(0, w, tile_size):
                win_h = min(tile_size, h - row)
                win_w = min(tile_size, w - col)
                window = Window(col, row, win_w, win_h)

                arr = src.read(1, window=window).astype(np.float32)

                mask = np.isfinite(arr)
                if src_nodata is not None:
                    mask &= arr != src_nodata

                if mask.sum() < min_pixels:
                    processed += 1
                    continue

                tile_std = float(arr[mask].std())
                if tile_std < min_std:
                    print(f"Rejected tile: std={tile_std:.3f} < min_std={min_std}")
                    processed += 1
                    continue

                try:
                    thr = float(threshold_otsu(arr[mask]))
                except Exception:
                    processed += 1
                    continue


                if max_threshold is not None and thr > max_threshold:
                    processed += 1
                    continue

                tile_centers_y.append(row + win_h / 2)
                tile_centers_x.append(col + win_w / 2)
                tile_thresholds.append(thr)
                processed += 1

                if processed % 16 == 0 or processed == total_tiles:
                    print(f"compute_tile_otsu_tif: {processed}/{total_tiles} tiles "
                          f"(valid so far: {len(tile_thresholds)}, last thr: {thr:.3f})")

    grid_y, grid_x = np.mgrid[0:h, 0:w]

    if not tile_thresholds:
        # No valid tiles found — scene has no detectable flood signal.
        # Use a conservative fallback that will produce near-zero detections
        # rather than flooding the whole image.
        print("|\t[WARN] No valid tiles found. Using conservative fallback (-0.4).")
        surface = np.full((h, w), -0.4, dtype=np.float32)
    else:
        print(f"compute_tile_otsu_tif: {len(tile_thresholds)} control points, "
              f"range [{min(tile_thresholds):.3f}, {max(tile_thresholds):.3f}]")

        points = np.column_stack([tile_centers_y, tile_centers_x])
        fallback = float(np.percentile(tile_thresholds, 10))

        if len(tile_thresholds) < 4 and max_threshold is not None:
            print(f"|\t[WARN] Apenas {len(tile_thresholds)} tiles válidos com ceiling={max_threshold:.3f}. A repetir sem ceiling...")
            return compute_tile_otsu_tif(
                src_band_path, out_tif, 
                tile_size, 
                interp_method, 
                interp_sigma, 
                min_pixels, 
                min_std,
                max_threshold=None
            )
        
        if len(tile_thresholds) >= 4:
            surface = griddata(points, tile_thresholds, (grid_y, grid_x),
                            method=interp_method, fill_value=fallback).astype(np.float32)
        else:
            surface = np.full((h, w), fallback, dtype=np.float32)


        surface = gaussian_filter(surface, sigma=interp_sigma)

    meta.update(driver='GTiff', dtype=rasterio.float32, count=1,
                compress='deflate', tiled=True, blockxsize=512, blockysize=512)
    with rasterio.open(out_tif, 'w', **meta) as dst:
        dst.write(surface, 1)

    print(f"compute_tile_otsu_tif: finished writing {out_tif}")
    return out_tif


def convertFileToTif(flood_dim: Path, out_tif: Path) -> None:
    """
    Reads the Flood.img band directly from the .data folder, preserving
    CRS, transform, and nodata, and writes a compressed tiled GeoTIFF.
    """
    data_folder = Path(str(flood_dim).replace(".dim", ".data"))
    flood_img = get_band_file(data_folder, "Flood")

    with rasterio.open(flood_img) as src:
        data = src.read(1)
        meta = src.meta.copy()

    flood_mask = (data == 1)
    clean_flood_mask = ndimage.binary_opening(flood_mask, structure=np.ones((3, 3)))

    labeled, n = label(clean_flood_mask)  # type: ignore[reportGeneralTypeIssues]
    sizes = ndimage.sum(clean_flood_mask, labeled, range(1, n + 1))
    remove_ids = np.where(sizes < 9)[0] + 1  # ajusta o limiar (em pixels)
    clean_flood_mask[np.isin(labeled, remove_ids)] = False

    data_clean = np.where(clean_flood_mask, 1, 0).astype(np.float32)
    data_clean[np.isnan(data)] = np.nan

    meta.update(
        driver="GTiff",
        dtype=rasterio.float32,
        count=1,
        compress="deflate",
        tiled=True
    )

    with rasterio.open(out_tif, "w", **meta) as dst:
        dst.write(data_clean, 1)

    print(f"|\tFlood mask exported to: {out_tif}")


def displayResults(dim_path: Path, flood_count: float, px_area_m2: float, total_area_m2: float) -> None:
    print("\n--- Flood Calculation Results ---")
    print(f"Product:                  {dim_path.name}")
    print(f"Number of Flooded Pixels: {flood_count:,}")
    print(f"Estimated Pixel Size:     ~{px_area_m2:,.2f} m^2")
    print(f"Total Flooded Area:       {total_area_m2:,.2f} m^2  ({total_area_m2 / 1_000_000:.3f} km^2)\n")