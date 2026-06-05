import os
import rasterio
import numpy as np
from rasterio.enums import Resampling

from S2.config import NODATA_VALUE
from S2.preview import save_preview_png, show_preview_window
from S2.processing import (
    compute_binary_area,
    compute_ndwi,
    compute_optimal_threshold,
    flood_map,
    water_mask,
    compute_scl_confidence_mask,  # Importado com sucesso
)
from S2.raster_io import debug, ensure_alignment, prepare_workspace, stats, write_raster


def _print_area(label, area_m2):
    print(f"{label}: {area_m2:,.2f} m2 ({area_m2 / 1_000_000.0:,.4f} km2)")


def run_pipeline(b3b_path, b8b_path, sclb_path, b3a_path, b8a_path, scla_path, work, preview=False, threshold=None):
    prepare_workspace(work)

    with rasterio.open(b3b_path) as ref_src:
        b3b_data = ref_src.read(1).astype("float32")
        profile = ref_src.profile.copy()

        # Alinhamento das bandas normais de 10m (usam Bilinear por padrão)
        b8b_data = ensure_alignment(ref_src, b8b_path)
        b3a_data = ensure_alignment(ref_src, b3a_path)
        b8a_data = ensure_alignment(ref_src, b8a_path)
        
        # Alinhamento e Resampling das bandas SCL (Força o Nearest Neighbor para manter integridade das classes)
        sclb_data = ensure_alignment(ref_src, sclb_path, resampling=Resampling.nearest)
        scla_data = ensure_alignment(ref_src, scla_path, resampling=Resampling.nearest)

    print("\nShapes:")
    print(f"B3B: {b3b_data.shape} | B8B: {b8b_data.shape} | B3A: {b3a_data.shape} | B8A: {b8a_data.shape}")
    print(f"SCL Before: {sclb_data.shape} | SCL After: {scla_data.shape} (Resampled para 10m)")

    debug("NDWI AND SCL CONFIDENCE")
    ndwi_before = compute_ndwi(b3b_data, b8b_data)
    ndwi_after = compute_ndwi(b3a_data, b8a_data)

    write_raster(os.path.join(work, "ndwi_before.tif"), ndwi_before, profile, NODATA_VALUE)
    write_raster(os.path.join(work, "ndwi_after.tif"), ndwi_after, profile, NODATA_VALUE)

    scl_conf_before = compute_scl_confidence_mask(sclb_data)
    scl_conf_after = compute_scl_confidence_mask(scla_data)

    # Gravar as matrizes de confiança originais da SCL (Float32 para decimais)
    profile_conf = profile.copy()
    profile_conf.update(dtype="float32")
    write_raster(os.path.join(work, "scl_conf_before.tif"), scl_conf_before, profile_conf, 0.0)
    write_raster(os.path.join(work, "scl_conf_after.tif"), scl_conf_after, profile_conf, 0.0)

    # Gravar cópia da SCL original a 10m para controlo visual rápido
    profile_scl = profile.copy()
    profile_scl.update(dtype="uint8")
    write_raster(os.path.join(work, "scl_before_10m.tif"), sclb_data.astype("uint8"), profile_scl, 0)
    write_raster(os.path.join(work, "scl_after_10m.tif"), scla_data.astype("uint8"), profile_scl, 0)

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
    # 1. Calcula a cheia de forma binária pura (0 e 1)
    flood_binary = flood_map(water_after, water_before)

    # 2. Multiplica a cheia pelos pesos da SCL (After) para embutir os valores na imagem final
    flood = flood_binary * scl_conf_after

    # Grava o flood.tif como Float32 para aguentar os novos decimais da SCL
    profile_flood = profile.copy()
    profile_flood.update(dtype="float32")
    write_raster(os.path.join(work, "flood.tif"), flood, profile_flood, 0.0)
    stats(flood, "NEW FLOOD WITH SCL VALUES", 0.0)

    debug("AREA")
    transform = profile["transform"]
    area_before = compute_binary_area(water_before, transform)
    area_after = compute_binary_area(water_after, transform)
    # A área calculada usa a máscara binária de píxeis afetados
    area_flood = compute_binary_area(flood_binary, transform)
    _print_area("Water BEFORE", area_before)
    _print_area("Water AFTER ", area_after)
    _print_area("New FLOOD   ", area_flood)

    if preview:
        preview_path = os.path.join(work, "preview.png")
        # As funções de visualização continuam a receber a versão binária para não partir os plots
        save_preview_png(
            preview_path,
            ndwi_before,
            ndwi_after,
            water_before,
            water_after,
            flood_binary,
            threshold=threshold,
        )
        print("Preview image:", os.path.abspath(preview_path))
        show_preview_window(
            ndwi_before,
            ndwi_after,
            water_before,
            water_after,
            flood_binary,
            threshold=threshold,
        )

    print("\nDONE ->", os.path.abspath(work))