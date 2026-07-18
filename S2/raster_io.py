from pathlib import Path

import numpy as np
import rasterio
import shutil
from rasterio.warp import Resampling, reproject

from .config import OUT_DIR


def debug(title: str) -> None:
	terminal_width = shutil.get_terminal_size().columns
	print("=" * terminal_width)
	print(title)
	print("=" * terminal_width)


def output_path(filename: str) -> Path:
	return OUT_DIR / filename


def prepare_workspace() -> None:
	"""Clear the output directory of all files except existing flood TIFs."""
	OUT_DIR.mkdir(parents=True, exist_ok=True)
	for item in OUT_DIR.iterdir():
		if item.is_dir():
			shutil.rmtree(item)
		elif not (item.suffix.lower() == ".tif" and "flood" in item.name.lower()):
			item.unlink()


def read_raster(path: str | Path) -> tuple[np.ndarray, dict]:
	with rasterio.open(path) as src:
		data = src.read(1).astype("float32")
		profile = src.profile.copy()
	return data, profile


def ensure_alignment(
	ref_src: rasterio.DatasetReader,
	src_path: str | Path,
	resampling: Resampling = Resampling.bilinear,
) -> np.ndarray:
	with rasterio.open(src_path) as src:
		needs_reproject = (
			src.crs != ref_src.crs
			or src.transform != ref_src.transform
			or src.width != ref_src.width
			or src.height != ref_src.height
		)
		if not needs_reproject:
			return src.read(1).astype("float32")

		print(f"Reprojecting: {Path(src.name).name} with method {resampling.name}")
		aligned = np.empty((ref_src.height, ref_src.width), dtype="float32")

		reproject(
			source=src.read(1),
			destination=aligned,
			src_transform=src.transform,
			src_crs=src.crs,
			dst_transform=ref_src.transform,
			dst_crs=ref_src.crs,
			resampling=resampling,
		)

		return aligned


def write_raster(path: Path, data: np.ndarray, profile: dict, nodata) -> None:
	"""Write a single-band GeoTIFF, respecting the dtype already set in profile."""
	out_profile = profile.copy()
	out_profile.update(driver="GTiff", dtype="float32", nodata=nodata, count=1, compress="lzw")

	with rasterio.open(path, "w", **out_profile) as dst:
		dst.write(data.astype("float32"), 1)


def stats(arr: np.ndarray, label: str, nodata) -> None:
	valid = arr[arr != nodata]

	print(f"\n[{label}]")
	if valid.size == 0:
		print("No valid pixels.")
		return
	
	print("MIN :", np.min(valid))
	print("MAX :", np.max(valid))
	print("MEAN:", np.mean(valid))