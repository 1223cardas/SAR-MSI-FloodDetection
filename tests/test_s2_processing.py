import numpy as np
from unittest.mock import patch

from S2.config import EPS, NODATA_VALUE, SCALE_FACTOR
from S2.discovery import checkEntryInOutput
from S2.processing import (
	compute_binary_area,
	compute_ndwi,
	compute_optimal_threshold,
	compute_scl_confidence_mask,
	flood_map,
	water_mask,
)
from processorsImpl import S2Processor


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


def test_compute_optimal_threshold_uses_default_for_small_samples():
	ndwi_before = np.array([[0.1, 0.2], [NODATA_VALUE, 0.3]], dtype="float32")
	ndwi_after = np.array([[0.4, 0.5], [0.6, NODATA_VALUE]], dtype="float32")

	result = compute_optimal_threshold(ndwi_before, ndwi_after, default_threshold=0.25)

	assert result == 0.25


def test_compute_scl_confidence_mask_maps_known_classes():
	scl = np.array(
		[[2, 3, 4], [5, 6, 8], [9, 10, 11]],
		dtype="uint8",
	)

	result = compute_scl_confidence_mask(scl)

	expected = np.array(
		[[0.8, 0.6, 0.3], [0.4, 1.0, 0.1], [0.1, 0.1, 0.2]],
		dtype="float32",
	)

	np.testing.assert_array_equal(result, expected)


def test_s2_processor_reuses_existing_flood_output(tmp_path):
	entry = {"collection": "sentinel-2-l2a", "place_query": "Kherson", "crisis_date": "2023-06-06", "processed_at": "2026-07-07_12-34-56"}
	_, _, cached_output = checkEntryInOutput(entry=entry)
	if cached_output is None:
		cached_output = tmp_path / f"{entry['place_query']}_{entry['processed_at']}_flood.tif"
	cached_output.touch()

	with patch("S2.config.OUT_DIR", tmp_path), patch("S2.discovery.discover_all_band_pairs") as mock_discovery, patch(
		"S2.pipeline.run_pipeline"
	) as mock_pipeline:
		result = S2Processor().run(
			run_processing=True,
			view=False,
			entry=entry,
		)

	assert result.output_path == cached_output
	mock_discovery.assert_not_called()
	mock_pipeline.assert_not_called()
