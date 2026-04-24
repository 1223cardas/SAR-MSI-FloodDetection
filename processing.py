import numpy as np

from config import EPS, NDWI_THRESHOLD, NODATA_VALUE, SCALE_FACTOR


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
    hist, bin_edges = np.histogram(valid, bins=256, range=(-1.0, 1.0))
    if hist.sum() == 0:
        return default_threshold

    probabilities = hist.astype("float64") / hist.sum()
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2.0

    cumulative_prob = np.cumsum(probabilities)
    cumulative_mean = np.cumsum(probabilities * bin_centers)
    total_mean = cumulative_mean[-1]

    between_var = (total_mean * cumulative_prob - cumulative_mean) ** 2
    denominator = cumulative_prob * (1.0 - cumulative_prob)
    between_var = np.divide(
        between_var,
        denominator,
        out=np.zeros_like(between_var),
        where=denominator > 0,
    )

    best_idx = int(np.argmax(between_var))
    return float(bin_centers[best_idx])


def water_mask(ndwi, threshold=NDWI_THRESHOLD):
    mask = np.zeros(ndwi.shape, dtype="uint8")
    valid = ndwi != NODATA_VALUE
    mask[valid & (ndwi > threshold)] = 1
    return mask


def flood_map(after, before):
    return ((after == 1) & (before == 0)).astype("uint8")


def compute_binary_area(mask, transform):
    pixel_area = abs((transform.a * transform.e) - (transform.b * transform.d))
    water_pixels = int(np.count_nonzero(mask == 1))
    return water_pixels * pixel_area
