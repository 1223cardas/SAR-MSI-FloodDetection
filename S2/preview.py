import os
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap

from .config import NDWI_THRESHOLD, NODATA_VALUE, OUT_DIR
from .processing import compute_optimal_threshold
from .raster_io import read_raster


def downsample_for_preview(arr, max_dim=1200):
	height, width = arr.shape[:2]
	largest = max(height, width)
	if largest <= max_dim:
		return arr

	step = int(np.ceil(largest / max_dim))
	return arr[::step, ::step]


def ndwi_preview_class(ndwi, threshold=NDWI_THRESHOLD):
	preview = np.where(ndwi == NODATA_VALUE, np.nan, 0.0).astype("float32")
	preview[(ndwi != NODATA_VALUE) & (ndwi > threshold)] = 1.0
	return preview


def build_preview_figure(ndwi_before, ndwi_after, water_before, water_after, flood, threshold=NDWI_THRESHOLD):
	ndwi_before = downsample_for_preview(ndwi_before)
	ndwi_after = downsample_for_preview(ndwi_after)
	water_before = downsample_for_preview(water_before)
	water_after = downsample_for_preview(water_after)
	flood = downsample_for_preview(flood)

	ndwi_before_vis = ndwi_preview_class(ndwi_before, threshold=threshold)
	ndwi_after_vis = ndwi_preview_class(ndwi_after, threshold=threshold)
	terrain_water_cmap = ListedColormap(["#d73027", "#2c7bb6"])

	fig, axes = plt.subplots(2, 3, figsize=(16, 10))
	axes = axes.ravel()

	im0 = axes[0].imshow(
		ndwi_before_vis,
		cmap=terrain_water_cmap,
		vmin=0,
		vmax=1,
		interpolation="nearest",
	)
	axes[0].set_title("NDWI Before (terrain / water)")
	axes[0].axis("off")
	fig.colorbar(
		im0,
		ax=axes[0],
		fraction=0.046,
		pad=0.04,
		ticks=[0, 1],
		label="0=terrain, 1=water",
	)

	im1 = axes[1].imshow(
		ndwi_after_vis,
		cmap=terrain_water_cmap,
		vmin=0,
		vmax=1,
		interpolation="nearest",
	)
	axes[1].set_title("NDWI After (terrain / water)")
	axes[1].axis("off")
	fig.colorbar(
		im1,
		ax=axes[1],
		fraction=0.046,
		pad=0.04,
		ticks=[0, 1],
		label="0=terrain, 1=water",
	)

	axes[2].imshow(flood, cmap="gray", vmin=0, vmax=1)
	axes[2].set_title("Flood")
	axes[2].axis("off")

	axes[3].imshow(water_before, cmap="Blues", vmin=0, vmax=1)
	axes[3].set_title("Water Before")
	axes[3].axis("off")

	axes[4].imshow(water_after, cmap="Blues", vmin=0, vmax=1)
	axes[4].set_title("Water After")
	axes[4].axis("off")

	axes[5].axis("off")
	axes[5].text(0.5, 0.5, "Result Preview", ha="center", va="center", fontsize=14)

	fig.tight_layout()
	return fig


def save_preview_png(
	path,
	ndwi_before,
	ndwi_after,
	water_before,
	water_after,
	flood,
	threshold=NDWI_THRESHOLD,
):
	fig = build_preview_figure(
		ndwi_before,
		ndwi_after,
		water_before,
		water_after,
		flood,
		threshold=threshold,
	)
	fig.savefig(path, dpi=180)
	plt.close(fig)


def show_preview_window(
	ndwi_before,
	ndwi_after,
	water_before,
	water_after,
	flood,
	threshold=NDWI_THRESHOLD,
):
	fig = build_preview_figure(
		ndwi_before,
		ndwi_after,
		water_before,
		water_after,
		flood,
		threshold=threshold,
	)
	plt.show()
	plt.close(fig)


def load_preview_results(out_dir=OUT_DIR, flood_path=None):
	ndwi_before, _ = read_raster(os.path.join(out_dir, "ndwi_before.tif"))
	ndwi_after, _ = read_raster(os.path.join(out_dir, "ndwi_after.tif"))
	water_before, _ = read_raster(os.path.join(out_dir, "water_before.tif"))
	water_after, _ = read_raster(os.path.join(out_dir, "water_after.tif"))
	if flood_path is not None:
		flood, _ = read_raster(str(flood_path))
		return ndwi_before, ndwi_after, water_before, water_after, flood

	flood_candidates = list(Path(out_dir).glob("*_flood.tif"))
	legacy_candidate = Path(out_dir) / "flood.tif"
	if legacy_candidate.exists():
		flood_candidates.append(legacy_candidate)

	if not flood_candidates:
		raise FileNotFoundError(f"No flood output found in {out_dir}")
	latest_candidate = max(flood_candidates, key=lambda path: path.stat().st_mtime)
	flood, _ = read_raster(str(latest_candidate))
	return ndwi_before, ndwi_after, water_before, water_after, flood


def preview_outputs_only(threshold=None, flood_path=None) -> Path | None:
	preview_path = os.path.join(OUT_DIR, "preview.png")
	ndwi_before, ndwi_after, water_before, water_after, flood = load_preview_results(OUT_DIR, flood_path=flood_path)

	if threshold is None:
		threshold = compute_optimal_threshold(ndwi_before, ndwi_after)

	save_preview_png(
		preview_path,
		ndwi_before,
		ndwi_after,
		water_before,
		water_after,
		flood,
		threshold=threshold,
	)
	print("Preview image:", os.path.abspath(preview_path))
	show_preview_window(
		ndwi_before,
		ndwi_after,
		water_before,
		water_after,
		flood,
		threshold=threshold,
	)
	print("\nPREVIEW ONLY ->", os.path.abspath(OUT_DIR))

	return Path(preview_path) if os.path.exists(preview_path) else None
