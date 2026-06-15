import numpy as np

from S2.config import EPS, NDWI_THRESHOLD, NODATA_VALUE, SCALE_FACTOR
from S2.processing import compute_binary_area, compute_ndwi, flood_map, water_mask


def test_compute_ndwi_marks_nodata_and_uses_scaled_values():
    green = np.array([[10000.0, 0.0], [5000.0, 2000.0]], dtype="float32")
    nir = np.array([[5000.0, 1000.0], [5000.0, 1000.0]], dtype="float32")

    result = compute_ndwi(green, nir)

    expected = np.full(green.shape, NODATA_VALUE, dtype="float32")
    expected[0, 0] = ((green[0, 0] / SCALE_FACTOR) - (nir[0, 0] / SCALE_FACTOR)) / (
        (green[0, 0] / SCALE_FACTOR) + (nir[0, 0] / SCALE_FACTOR) + EPS
    )
    expected[1, 0] = ((green[1, 0] / SCALE_FACTOR) - (nir[1, 0] / SCALE_FACTOR)) / (
        (green[1, 0] / SCALE_FACTOR) + (nir[1, 0] / SCALE_FACTOR) + EPS
    )
    expected[1, 1] = ((green[1, 1] / SCALE_FACTOR) - (nir[1, 1] / SCALE_FACTOR)) / (
        (green[1, 1] / SCALE_FACTOR) + (nir[1, 1] / SCALE_FACTOR) + EPS
    )

    np.testing.assert_allclose(result, expected, rtol=1e-6, atol=1e-6)


def test_water_mask_uses_threshold_and_nodata():
    ndwi = np.array([[0.2, 0.0], [NODATA_VALUE, 0.8]], dtype="float32")

    result = water_mask(ndwi, threshold=0.1)

    expected = np.array([[1, 0], [0, 1]], dtype="uint8")
    np.testing.assert_array_equal(result, expected)


def test_flood_map_detects_new_water_only():
    before = np.array([[0, 1], [0, 0]], dtype="uint8")
    after = np.array([[1, 1], [0, 1]], dtype="uint8")

    result = flood_map(after, before)

    expected = np.array([[1, 0], [0, 1]], dtype="uint8")
    np.testing.assert_array_equal(result, expected)


def test_compute_binary_area_counts_pixels():
    class DummyTransform:
        a = 10.0
        b = 0.0
        d = 0.0
        e = -10.0

    mask = np.array([[1, 0], [1, 1]], dtype="uint8")

    result = compute_binary_area(mask, DummyTransform())

    assert result == 300.0
