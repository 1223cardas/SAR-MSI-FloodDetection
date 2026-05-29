import math

# Approximate kilometers per degree at the equator / per degree latitude
# 1 degree latitude ~= 110.574 km
# 1 degree longitude ~= 111.320 km
KM_PER_DEG_LAT = 110.574
KM_PER_DEG_LON = 111.320


def compute_bbox(center_lat: float, center_lon: float, size_km: float) -> list:
	try:
		half = size_km / 2.0
		dlat = half / KM_PER_DEG_LAT
		cos_lat = math.cos(math.radians(center_lat))

		dlon = half / (KM_PER_DEG_LON * cos_lat)

		min_lon = center_lon - dlon
		min_lat = center_lat - dlat
		max_lon = center_lon + dlon
		max_lat = center_lat + dlat

		bbox = [min_lon, min_lat, max_lon, max_lat]

		return bbox
	except ValueError as e:
		print(f"Error: {e}")
		return []
