from datetime import datetime

import numpy as np
import numpy.ma as ma
from rasterio.crs import CRS
from rasterio.transform import from_origin

from common.shared_models import Product
from S1.Processing.modules import paths as s1_paths
from S1.Processing.modules.masking import computeFloodArea
from S1.Processing.modules.paths import build_output_file, checkEntryInOutput
from S1.Processing.modules.pclasses import ProductData


def test_product_extractDateFromProduct_parses_acquisition_time():
	product = Product(
		name="S1A_IW_GRDH_1SDV_20210101T123456_20210101T123456_012345_67890_ABCDE.SAFE"
	)

	product.extractDateFromProduct()

	assert product.date == datetime(2021, 1, 1, 12, 34, 56)


def test_build_output_file_uses_configured_output_directory(tmp_path, monkeypatch):
	monkeypatch.setitem(s1_paths.paths, "out", tmp_path)

	result = build_output_file("scene_flood.tif")

	assert result == tmp_path / "scene_flood.tif"


def test_checkEntryInOutput_without_previous_timestamp_builds_new_name():
	entry = {"place_query": "Kherson", "processed_at": ""}

	name, timestamp, existing = checkEntryInOutput(entry)

	assert existing is None
	assert name == f"Kherson_{timestamp}_flood"


def test_computeFloodArea_counts_flood_pixels_and_area():
	band = ma.masked_array(np.ones((5, 5), dtype=np.float32), mask=np.zeros((5, 5), dtype=bool))
	data = ProductData(
		band=band,
		transform=from_origin(0, 50, 10, 10),
		crs=CRS.from_epsg(32629),
		height=5,
		width=5,
	)

	flood_count, px_area_m2, total_area_m2 = computeFloodArea(data)

	assert flood_count == 25
	assert px_area_m2 == 100.0
	assert total_area_m2 == 2500.0