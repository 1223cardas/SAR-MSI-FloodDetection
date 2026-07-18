import numpy as np

from .config import EPS, NDWI_THRESHOLD, NODATA_VALUE, SCALE_FACTOR
from skimage.filters import threshold_otsu


def compute_ndwi(green_band, nir_band):
	green = green_band / SCALE_FACTOR
	nir = nir_band / SCALE_FACTOR

	ndwi = np.full(green.shape, NODATA_VALUE, dtype="float32")
	mask = (green > 0) & (nir > 0)
	ndwi[mask] = (green[mask] - nir[mask]) / (green[mask] + nir[mask] + EPS)
	return ndwi


def compute_optimal_threshold(ndwi_before, ndwi_after, default_threshold=NDWI_THRESHOLD):
	valid_before = ndwi_before[(ndwi_before != NODATA_VALUE) & np.isfinite(ndwi_before)]
	valid_after = ndwi_after[(ndwi_after != NODATA_VALUE) & np.isfinite(ndwi_after)]
	valid = np.concatenate([valid_before, valid_after])

	if valid.size < 32:
		return default_threshold

	valid = np.clip(valid, -1.0, 1.0)
	return float(threshold_otsu(valid))


def water_mask(ndwi, threshold=NDWI_THRESHOLD):
	mask = np.zeros(ndwi.shape, dtype="uint8")
	valid = ndwi != NODATA_VALUE
	mask[valid & (ndwi > threshold)] = 1
	return mask


def flood_map(after, before):
	"""Generates the base binary flood mask (1 = New flood, 0 = Dry/Same)"""
	return ((after == 1) & (before == 0)).astype("uint8")


def compute_binary_area(mask, transform):
	pixel_area = abs((transform.a * transform.e) - (transform.b * transform.d))
	water_pixels = int(np.count_nonzero(mask == 1))
	return water_pixels * pixel_area


def compute_scl_confidence_mask(scl_data):
	confidence = np.zeros_like(scl_data, dtype=np.float32)

	# Atmospheric noise — very low confidence
	confidence[(scl_data == 8) | (scl_data == 9)] = 0.1    # cloud medium/high
	confidence[(scl_data == 10)] = 0.1                     # thin cirrus

	# Low confidence
	confidence[(scl_data == 11)] = 0.2                     # snow/ice
	confidence[(scl_data == 4)] = 0.3                      # vegetation
	
	# Ambiguous — medium-low confidence
	confidence[(scl_data == 5)] = 0.4                      # bare soil
	confidence[(scl_data == 3)] = 0.6                      # cloud shadow

	# Probable — medium-high confidence
	confidence[(scl_data == 2)] = 0.8                      # dark area

	# Confirmed — full confidence
	confidence[scl_data == 6] = 1.0                        # water

	return confidence