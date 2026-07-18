from rasterio.enums import Resampling
import numpy as np
import rasterio
import os
import time

from .config import NODATA_VALUE, OUT_DIR
from .preview import save_preview_png, show_preview_window
from .processing import *
from .raster_io import debug, ensure_alignment, output_path, prepare_workspace, stats, write_raster


def _print_area(label, area_m2):
	print(f"{label}: {area_m2:,.2f} m2 ({area_m2 / 1_000_000.0:,.4f} km2)")


def _should_stop_or_pause(stop_event, pause_event, progress_callback=None, fraction=0.0, message="Paused"):
	if stop_event is not None and stop_event.is_set():
		return True
	if pause_event is None or not pause_event.is_set():
		return False
	if progress_callback is not None:
		progress_callback(fraction, message)
	while pause_event.is_set():
		if stop_event is not None and stop_event.is_set():
			if progress_callback is not None:
				progress_callback(fraction, "Cancelled")
			return True
		time.sleep(0.2)
	return stop_event is not None and stop_event.is_set()


def _emit(progress_callback, fraction, message):
	if progress_callback is not None:
		progress_callback(fraction, message)


def _write_google_earth_overlay(path, flood, ref_profile):
	visible = np.isfinite(flood) & (flood > 0)

	rgb = np.zeros((3,) + flood.shape, dtype="uint8")
	if np.any(visible):
		valid = flood[visible]
		vmin = float(valid.min())
		vmax = float(valid.max())
		if vmax <= vmin:
			vmax = vmin + 1.0

		normalized = np.zeros(flood.shape, dtype="float32")
		normalized[visible] = (flood[visible] - vmin) / (vmax - vmin)
		shade = (np.clip(normalized, 0.0, 1.0) * 255).astype("uint8")
		rgb[0] = shade
		rgb[1] = shade
		rgb[2] = shade

	alpha = np.where(visible, 255, 0).astype("uint8")
	rgba = np.vstack([rgb, alpha[np.newaxis, :, :]])

	profile = ref_profile.copy()
	profile.update(
		driver="GTiff",
		dtype="uint8",
		count=4,
		compress="lzw",
		photometric="RGB",
		nodata=None,
	)

	with rasterio.open(path, "w", **profile) as dst:
		dst.write(rgba)


def run_pipeline(
	before,
	after,
	output_name="flood.tif",
	preview=False,
	threshold=None,
	progress_callback=None,
	stop_event=None,
	pause_event=None,
):
	prepare_workspace()

	_emit(progress_callback, 0.0, "Preparing S2 workspace")

	if _should_stop_or_pause(stop_event, pause_event, progress_callback, 0.0):
		return

	with rasterio.open(before.b3) as ref_src:
		b3b_data = ref_src.read(1).astype("float32")
		profile = ref_src.profile.copy()

		# Alignment of standard 10m bands (uses Bilinear by default)
		b8b_data = ensure_alignment(ref_src, before.b8)
		_emit(progress_callback, 0.12, "Aligning S2 bands")
		if _should_stop_or_pause(stop_event, pause_event, progress_callback, 0.12):
			return
		b3a_data = ensure_alignment(ref_src, after.b3)
		b8a_data = ensure_alignment(ref_src, after.b8)
		
		# Alignment and Resampling of SCL bands (Forces Nearest Neighbor to maintain class integrity)
		sclb_data = ensure_alignment(ref_src, before.scl, resampling=Resampling.nearest)
		scla_data = ensure_alignment(ref_src, after.scl, resampling=Resampling.nearest)

	_emit(progress_callback, 0.22, "S2 bands aligned")
	if _should_stop_or_pause(stop_event, pause_event, progress_callback, 0.22):
		return

	print("\nShapes:")
	print(f"B3B: {b3b_data.shape} | B8B: {b8b_data.shape} | B3A: {b3a_data.shape} | B8A: {b8a_data.shape}")
	print(f"SCL Before: {sclb_data.shape} | SCL After: {scla_data.shape} (Resampled to 10m)")

	debug("NDWI AND SCL CONFIDENCE")
	ndwi_before = compute_ndwi(b3b_data, b8b_data)
	ndwi_after = compute_ndwi(b3a_data, b8a_data)
	_emit(progress_callback, 0.35, "NDWI calculated")
	if _should_stop_or_pause(stop_event, pause_event, progress_callback, 0.35):
		return

	write_raster(output_path("ndwi_before.tif"), ndwi_before, profile, NODATA_VALUE)
	write_raster(output_path("ndwi_after.tif"), ndwi_after, profile, NODATA_VALUE)

	scl_conf_before = compute_scl_confidence_mask(sclb_data)
	scl_conf_after = compute_scl_confidence_mask(scla_data)
	_emit(progress_callback, 0.5, "SCL confidence calculated")
	if _should_stop_or_pause(stop_event, pause_event, progress_callback, 0.5):
		return

	# Save original SCL confidence matrices (Float32 for decimals)
	profile_conf = profile.copy()
	profile_conf.update(dtype="float32")
	write_raster(output_path("scl_conf_before.tif"), scl_conf_before, profile_conf, 0.0)
	write_raster(output_path("scl_conf_after.tif"), scl_conf_after, profile_conf, 0.0)

	# Save copy of original SCL at 10m for quick visual check
	profile_scl = profile.copy()
	profile_scl.update(dtype="uint8")
	write_raster(output_path("scl_before_10m.tif"), sclb_data.astype("uint8"), profile_scl, 0)
	write_raster(output_path("scl_after_10m.tif"), scla_data.astype("uint8"), profile_scl, 0)

	stats(ndwi_before, "NDWI BEFORE", NODATA_VALUE)
	stats(ndwi_after, "NDWI AFTER", NODATA_VALUE)

	if threshold is None:
		threshold = compute_optimal_threshold(ndwi_before, ndwi_after)
		print(f"\nThreshold mode: AUTO (Otsu) -> {threshold:.4f}")
	else:
		print(f"\nThreshold mode: MANUAL -> {threshold:.4f}")

	_emit(progress_callback, 0.65, "Threshold set")
	if _should_stop_or_pause(stop_event, pause_event, progress_callback, 0.65):
		return

	debug("WATER MASK")
	water_before = water_mask(ndwi_before, threshold=threshold)
	water_after = water_mask(ndwi_after, threshold=threshold)
	_emit(progress_callback, 0.75, "Water masks created")
	if _should_stop_or_pause(stop_event, pause_event, progress_callback, 0.75):
		return

	write_raster(output_path("water_before.tif"), water_before, profile, 0)
	write_raster(output_path("water_after.tif"), water_after, profile, 0)

	stats(water_before, "WATER BEFORE", 0)
	stats(water_after, "WATER AFTER", 0)

	debug("FLOOD")
	# 1. Calculate the flood purely in binary (0 and 1)
	flood_binary = flood_map(water_after, water_before)

	# 2. Multiply the flood by the SCL weights (After) to embed the values in the final image
	flood = flood_binary * scl_conf_after

	# Save flood.tif as Float32 to handle the new SCL decimals
	profile_flood = profile.copy()
	profile_flood.update(dtype="float32")
	write_raster(output_path(output_name), flood, profile_flood, 0.0)
	overlay_name = os.path.splitext(output_name)[0] + "_google_earth.tif"
	_write_google_earth_overlay(output_path(overlay_name), flood, profile_flood)
	stats(flood, "NEW FLOOD WITH SCL VALUES", 0.0)
	_emit(progress_callback, 0.9, "Flood calculated and saved")
	if _should_stop_or_pause(stop_event, pause_event, progress_callback, 0.9):
		return

	debug("AREA")
	transform = profile["transform"]
	area_before = compute_binary_area(water_before, transform)
	area_after = compute_binary_area(water_after, transform)
	# The calculated area uses the binary mask of affected pixels
	area_flood = compute_binary_area(flood_binary, transform)
	_print_area("Water BEFORE", area_before)
	_print_area("Water AFTER ", area_after)
	_print_area("FLOOD   ", area_flood)

	if preview:
		_emit(progress_callback, 0.95, "Generating preview")
		if _should_stop_or_pause(stop_event, pause_event, progress_callback, 0.95):
			return
		preview_path = output_path("preview.png")
		# The visualization functions continue to receive the binary version to avoid breaking the plots
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

	_emit(progress_callback, 1.0, "S2 completed")
	print("\nDONE ->", os.path.abspath(OUT_DIR))