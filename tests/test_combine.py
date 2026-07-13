from pathlib import Path

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_origin

from Combined.combine import fuse_flood_bits, fuse_flood_outputs


def _write_raster(path: Path, data: np.ndarray) -> None:
    profile = {
        "driver": "GTiff",
        "height": data.shape[0],
        "width": data.shape[1],
        "count": 1,
        "dtype": data.dtype,
        "crs": CRS.from_epsg(32629),
        "transform": from_origin(0, 20, 10, 10),
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data, 1)


def test_fuse_flood_bits_sums_continuous_weights():
    s1 = np.ones((20, 20), dtype="uint8")
    s2 = np.full((20, 20), 0.25, dtype="float32")
    s2[0, 0] = 0.0
    s2[1, 1] = 2.0

    result = fuse_flood_bits(s1, s2)

    expected = np.full((20, 20), 0.25, dtype="float32")
    expected[0, 0] = 0.5
    expected[1, 1] = 2.0
    np.testing.assert_allclose(result, expected)


def test_fuse_flood_outputs_writes_float32_sum(tmp_path: Path):
    s1_path = tmp_path / "s1_flood.tif"
    s2_path = tmp_path / "s2_flood.tif"
    out_path = tmp_path / "fused.tif"

    s1 = np.ones((20, 20), dtype="uint8")
    s2 = np.full((20, 20), 0.25, dtype="float32")
    s2[0, 0] = 0.0
    s2[1, 1] = 2.0

    _write_raster(s1_path, s1)
    _write_raster(s2_path, s2)

    result_path = fuse_flood_outputs(s1_path, s2_path, out_path)

    assert result_path == out_path
    with rasterio.open(result_path) as src:
        assert src.dtypes[0] == "float32"
        data = src.read(1)

    expected = np.full((20, 20), 0.25, dtype="float32")
    expected[0, 0] = 0.5
    expected[1, 1] = 2.0
    np.testing.assert_allclose(data, expected)