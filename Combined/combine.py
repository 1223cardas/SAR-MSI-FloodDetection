from __future__ import annotations

from pathlib import Path
import numpy as np
import rasterio
from rasterio.warp import Resampling, reproject
import threading
from matplotlib import colormaps
from matplotlib import colors as mcolors


def _should_stop(stop_event: threading.Event | None, pause_event: threading.Event | None, progress_callback=None, fraction: float = 0.0) -> bool:
	"""Check execution status flags and handle pipeline interruptions."""
	if stop_event and stop_event.is_set():
		if progress_callback:
			progress_callback(fraction, "Cancelled")
		return True

	if pause_event and pause_event.is_set():
		if progress_callback:
			progress_callback(fraction, "Paused")
		while pause_event.is_set():
			if stop_event and stop_event.is_set():
				if progress_callback:
					progress_callback(fraction, "Cancelled")
				return True
			threading.Event().wait(0.2)

	return False


def _load_raster(path: Path) -> tuple[np.ndarray, dict]:
	"""Load a geospatial raster band directly into a floating point NumPy matrix."""
	with rasterio.open(path) as src:
		data = src.read(1).astype("float32")
		profile = src.profile.copy()
	return data, profile


def _align_to_reference(data: np.ndarray, source_profile: dict, reference_profile: dict) -> np.ndarray:
	"""Reproject and align geospatial source data matching the reference grid context."""
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


def fuse_flood_bits(s1_flood: np.ndarray, s2_flood: np.ndarray,
					min_blob_px: int = 200) -> np.ndarray:
	from scipy.ndimage import label, binary_opening

	s1 = np.where(np.isfinite(s1_flood) & (s1_flood > 0), 1.0, 0.0).astype("float32")
	s2 = np.where(np.isfinite(s2_flood), s2_flood, 0.0).astype("float32")
	s2_available = (s2 > 0.1).astype("float32")

	fused = np.where(
		s2_available > 0,
		s1 * s2,
		s1 * 0.5
	).astype("float32")

	# Remove isolated small blobs — these are field-level false positives,
	# not spatially coherent flood bodies
	flood_binary = (fused > 0).astype(bool)
	flood_binary = binary_opening(flood_binary, structure=np.ones((3, 3)))

	labeled, n = label(flood_binary) # type:ignore
	if n > 0:
		from scipy.ndimage import sum as nd_sum
		sizes = nd_sum(flood_binary, labeled, range(1, n + 1))
		remove = np.where(np.array(sizes) < min_blob_px)[0] + 1
		flood_binary[np.isin(labeled, remove)] = False

	# Zero out the fused values where blobs were removed
	fused[~flood_binary] = 0.0 # type:ignore

	return fused


def fuse_flood_outputs(
	s1_flood_path: Path,
	s2_flood_path: Path,
	output_path: Path,
	progress_callback=None,
	stop_event=None,
	pause_event=None,
) -> Path:
	"""Fuse S1 and S2 flood outputs and save a float32 continuous confidence map."""
	progress = progress_callback or (lambda *_args, **_kwargs: None)

	if _should_stop(stop_event, pause_event, progress_callback, 0.0):
		return output_path

	progress(0.15, "Loading S1 raster...")
	s1_data, s1_profile = _load_raster(s1_flood_path)
	if _should_stop(stop_event, pause_event, progress_callback, 0.15):
		return output_path

	progress(0.3, "Loading S2 raster...")
	s2_data, s2_profile = _load_raster(s2_flood_path)
	if _should_stop(stop_event, pause_event, progress_callback, 0.3):
		return output_path
	
	progress(0.55, "Aligning S2 raster with S1...")
	s2_data = _align_to_reference(s2_data, s2_profile, s1_profile)
	if _should_stop(stop_event, pause_event, progress_callback, 0.55):
		return output_path

	progress(0.75, "Fusing rasters...")
	fused_continuous = fuse_flood_bits(s1_data, s2_data)
	if _should_stop(stop_event, pause_event, progress_callback, 0.75):
		return output_path

	output_profile = s1_profile.copy()
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

	# Also write a separate colorized RGB(A) GeoTIFF for overlay use.
	try:
		color_path = output_path.with_name(output_path.stem + ".color.tif")
		finite = np.isfinite(fused_continuous)
		if finite.any():
			valid = fused_continuous[finite]
			vmin = float(valid.min())
			vmax = float(valid.max())
			if vmax <= vmin:
				vmax = vmin + 1.0

			norm = mcolors.Normalize(vmin=vmin, vmax=vmax, clip=True)
			cmap = colormaps["viridis"]
			rgba = cmap(norm(np.nan_to_num(fused_continuous, nan=vmin)))

			rgb = (rgba[:, :, :3] * 255).astype("uint8")
			transparent_mask = (~finite) | (fused_continuous == 0)
			alpha = np.where(transparent_mask, 0, 255).astype("uint8")

			rgb_bands = np.transpose(rgb, (2, 0, 1))
			alpha_band = alpha[np.newaxis, :, :]
			rgba_bands = np.vstack([rgb_bands, alpha_band])

			color_profile = s1_profile.copy()
			color_profile.update(
				driver="GTiff",
				dtype="uint8",
				count=4,
				compress="lzw",
				photometric="RGB",
				nodata=None,
			)

			with rasterio.open(color_path, "w", **color_profile) as dstc:
				dstc.write(rgba_bands)

			print(f"[FUSION] Success! Colorized overlay saved at: {color_path.name}")
	except Exception as e:
		print(f"[FUSION] Warning: failed to write colorized overlay GeoTIFF: {e}")

	progress(1.0, "Fusion complete")

	print(f"\n[FUSION] Success! Continuous scale file saved at: {output_path.name}")

	unique_values = np.unique(fused_continuous)
	formatted_values = [
		str(int(value)) if np.isclose(value, round(value)) else f"{value:g}"
		for value in unique_values
	]
	print(f" -> Unique values generated during fusion: [{', '.join(formatted_values)}]")

	return output_path