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


def compute_optimal_threshold(ndwi_before, ndwi_after, default_threshold=NDWI_THRESHOLD, progress_callback=None, stop_event=None, pause_event=None):
    if stop_event is not None and stop_event.is_set():
        return default_threshold
    while pause_event is not None and pause_event.is_set():
        if stop_event is not None and stop_event.is_set():
            return default_threshold
        import threading
        threading.Event().wait(0.2)

    valid_before = ndwi_before[(ndwi_before != NODATA_VALUE) & np.isfinite(ndwi_before)]
    valid_after = ndwi_after[(ndwi_after != NODATA_VALUE) & np.isfinite(ndwi_after)]
    valid = np.concatenate([valid_before, valid_after])

    if valid.size < 32:
        return default_threshold

    valid = np.clip(valid, -1.0, 1.0)
    if threshold_otsu is None:
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

    return float(threshold_otsu(valid))


def water_mask(ndwi, threshold=NDWI_THRESHOLD):
    mask = np.zeros(ndwi.shape, dtype="uint8")
    valid = ndwi != NODATA_VALUE
    mask[valid & (ndwi > threshold)] = 1
    return mask


def flood_map(after, before):
    """Gera a máscara binária base de inundação (1 = Nova inundação, 0 = Seco/Igual)"""
    return ((after == 1) & (before == 0)).astype("uint8")


def compute_binary_area(mask, transform):
    pixel_area = abs((transform.a * transform.e) - (transform.b * transform.d))
    water_pixels = int(np.count_nonzero(mask == 1))
    return water_pixels * pixel_area


# def compute_scl_confidence_mask(scl_data):
#     # Inicializa a matriz com 0.0 (Classes neutras ou sem dados: 0, 1, 7, 11)
#     confidence = np.zeros_like(scl_data, dtype=np.float32)

#     confidence[
#         (scl_data == 8) | 
#         (scl_data == 9) 
#     ] = 0.1

#     confidence[(scl_data == 3) | (scl_data == 10) | (scl_data == 5)] = 0.2

#     confidence[(scl_data == 4) | (scl_data == 11)] = 0.4

#     confidence[(scl_data == 2)] = 0.6

#     confidence[scl_data == 6] = 1.0

#     return confidence


def compute_scl_confidence_mask(scl_data):
    confidence = np.zeros_like(scl_data, dtype=np.float32)

    # Atmospheric noise — very low confidence
    confidence[(scl_data == 8) | (scl_data == 9)] = 0.1   # cloud medium/high
    confidence[(scl_data == 10)] = 0.1                     # thin cirrus

    # Ambiguous — low confidence
    confidence[(scl_data == 3)] = 0.2                      # cloud shadow
    confidence[(scl_data == 2)] = 0.2                      # dark area (was 0.6 — shadows look like water)
    confidence[(scl_data == 5)] = 0.2                      # unclassified

    # Probable — medium confidence
    confidence[(scl_data == 4)] = 0.5                      # vegetation
    confidence[(scl_data == 11)] = 0.5                     # snow/ice

    # Confirmed — full confidence
    confidence[scl_data == 6] = 1.0                        # water

    return confidence