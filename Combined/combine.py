from __future__ import annotations

from pathlib import Path
import numpy as np
import rasterio
from rasterio.warp import Resampling, reproject
import threading


def _should_stop(stop_event, pause_event, progress_callback=None, fraction=0.0):
    if stop_event is not None and stop_event.is_set():
        if progress_callback is not None:
            progress_callback(fraction, "Cancelado")
        return True
    if pause_event is not None and pause_event.is_set():
        if progress_callback is not None:
            progress_callback(fraction, "Pausado")
        while pause_event.is_set():
            if stop_event is not None and stop_event.is_set():
                if progress_callback is not None:
                    progress_callback(fraction, "Cancelado")
                return True
            threading.Event().wait(0.2)
    return stop_event is not None and stop_event.is_set()


def _load_raster(path: Path) -> tuple[np.ndarray, dict]:
    with rasterio.open(path) as src:
        data = src.read(1).astype("float32")
        profile = src.profile.copy()
    return data, profile


def _align_to_reference(data: np.ndarray, source_profile: dict, reference_profile: dict) -> np.ndarray:
    same_grid = (
        source_profile.get("crs") == reference_profile.get("crs")
        and source_profile.get("transform") == reference_profile.get("transform")
        and source_profile.get("width") == reference_profile.get("width")
        and source_profile.get("height") == reference_profile.get("height")
    )

    if same_grid:
        return data

    aligned = np.zeros(
        (int(reference_profile["height"]), int(reference_profile["width"])),
        dtype="float32",
    )
    reproject(
        source=data,
        destination=aligned,
        src_transform=source_profile["transform"],
        src_crs=source_profile["crs"],
        dst_transform=reference_profile["transform"],
        dst_crs=reference_profile["crs"],
        resampling=Resampling.nearest,
    )
    return aligned


def fuse_flood_bits(s1_flood: np.ndarray, s2_flood: np.ndarray) -> np.ndarray:
    if s1_flood.shape != s2_flood.shape:
        raise ValueError("Flood rasters must have the same shape before fusion")

    # S1 contributes as binary water mask (0 or 1)
    s1_bits = np.where(np.isfinite(s1_flood) & (s1_flood > 0), 1.0, 0.0).astype("float32")

    # S2 values are preserved as continuous confidences/classes
    s2_weights = np.where(np.isfinite(s2_flood), s2_flood, 0.0).astype("float32")

    return s1_bits + s2_weights


def fuse_flood_outputs(
    s1_flood_path: str | Path,
    s2_flood_path: str | Path,
    output_path: str | Path | None = None,
    progress_callback=None,
    stop_event=None,
    pause_event=None,
) -> Path:
    """Fuse S1 and S2 flood outputs and save a float32 continuous confidence map."""
    s1_flood_path = Path(s1_flood_path)
    s2_flood_path = Path(s2_flood_path)
    output_path = Path(output_path) if output_path is not None else s1_flood_path.with_name("flood_fused_continuous.tif")

    if _should_stop(stop_event, pause_event, progress_callback, 0.0):
        return output_path

    s1_data, s1_profile = _load_raster(s1_flood_path)
    if progress_callback is not None:
        progress_callback(0.15, "A carregar raster S1")
    if _should_stop(stop_event, pause_event, progress_callback, 0.15):
        return output_path

    s2_data, s2_profile = _load_raster(s2_flood_path)
    if progress_callback is not None:
        progress_callback(0.3, "A carregar raster S2")
    if _should_stop(stop_event, pause_event, progress_callback, 0.3):
        return output_path
    
    s2_data = _align_to_reference(s2_data, s2_profile, s1_profile)
    if progress_callback is not None:
        progress_callback(0.55, "A alinhar raster S2")
    if _should_stop(stop_event, pause_event, progress_callback, 0.55):
        return output_path

    fused_continuous = fuse_flood_bits(s1_data, s2_data)
    if progress_callback is not None:
        progress_callback(0.75, "A fundir rasters")
    if _should_stop(stop_event, pause_event, progress_callback, 0.75):
        return output_path

    output_profile = s1_profile.copy()
    output_profile.pop("nodata", None)
    output_profile.update(
        driver="GTiff",
        dtype="float32",
        count=1,
        compress="lzw",
        nodata=0.0,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output_path, "w", **output_profile) as dst:
        dst.write(fused_continuous, 1)

    if progress_callback is not None:
        progress_callback(1.0, "Fusão concluída")

    print(f"\n[FUSION] Concluído! Ficheiro de escala contínua guardado em: {output_path.name}")
    print(f" -> Valores únicos gerados na fusão: {np.unique(fused_continuous)}")

    return output_path