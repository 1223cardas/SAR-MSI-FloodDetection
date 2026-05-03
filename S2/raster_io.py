import os
import shutil

import numpy as np
import rasterio
from rasterio.warp import Resampling, reproject


def debug(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def prepare_workspace(folder):
    if os.path.exists(folder):
        shutil.rmtree(folder)
    os.makedirs(folder)


def read_raster(path):
    with rasterio.open(path) as src:
        data = src.read(1).astype("float32")
        profile = src.profile.copy()
    return data, profile


def ensure_alignment(ref_src, src_path):
    with rasterio.open(src_path) as src:
        if (
            src.crs != ref_src.crs
            or src.transform != ref_src.transform
            or src.width != ref_src.width
            or src.height != ref_src.height
        ):
            print(f"Reprojecting: {os.path.basename(src.name)}")

            data = src.read(1)
            aligned = np.empty((ref_src.height, ref_src.width), dtype="float32")

            reproject(
                source=data,
                destination=aligned,
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=ref_src.transform,
                dst_crs=ref_src.crs,
                resampling=Resampling.bilinear,
            )
            return aligned

        return src.read(1).astype("float32")


def write_raster(path, data, ref_profile, nodata):
    profile = ref_profile.copy()
    profile.update(
        driver="GTiff",
        dtype="float32",
        nodata=nodata,
        count=1,
        compress="lzw",
    )

    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data.astype("float32"), 1)


def stats(arr, label, nodata):
    valid = arr[arr != nodata]

    print(f"\n[{label}]")
    if valid.size == 0:
        print("No valid pixels.")
        return

    print("MIN :", np.min(valid))
    print("MAX :", np.max(valid))
    print("MEAN:", np.mean(valid))
