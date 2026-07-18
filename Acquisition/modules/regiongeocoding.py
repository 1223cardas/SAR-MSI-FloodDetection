from geopy.geocoders import Nominatim
import math

from .aclasses import Place, BBox, LogEntry
from .acquisition_config import *


def _requestRegionInfo(region_name: str, geolocator: Nominatim) -> list[Place]:
	try:
		print(f"Requesting geocoding info for '{region_name}'...")
		locations = geolocator.geocode(
			region_name,
			exactly_one=False,
			limit=DEFAULT_SEARCH_LIMIT,
			language=NOMINATIM_LANGUAGE # type: ignore[call-arg]
		)

		if not locations or locations is None:
			print(f"No geocoding results found for {region_name}. Try a different name.")
			return []
		
		places = []
		for loc in locations: # type: ignore[call-arg]
			raw: dict = loc.raw
			display_name = raw.get("display_name") or "N/A"

			places.append(
				Place(display_name, loc.latitude, loc.longitude)
			)

		return places
	except Exception as e:
		print(f"Error requesting region info: {e}")
		raise


def _displayMatches(places: list[Place], region: str):
	print(f"Matches with {region}:")
	for idx, place in enumerate(places, start=1):
		print(f"\t[{idx}] {place.name} (lat={place.lat}, lon={place.lon})")


def _selectPlace(places: list[Place]) -> Place | None:
	while True:
		selection = input("Select a region by entering the corresponding number. (or 'b' to choose another region)")
		if selection.lower() == 'b':
			return None

		try:
			selected_index = int(selection) - 1
			if selected_index not in range(0, len(places)):
				print("Selection out of range. Please enter a valid number.")
				continue
			
			place = places[selected_index]
		except ValueError:
			print("Invalid input. Please enter a number.")
			continue

		while True:
			confirm = input(f"Use '{place.name}'? [y/n]:")
			if confirm.lower() == 'n':
				break
			elif confirm.lower() == 'y':
				return place
			else:
				print("Invalid input. Please enter 'y' or 'n'")
				continue


def _compute_bbox(place: Place, size_km: float) -> list[float]:
	try:
		half = size_km / 2.0
		dlat = half / KM_PER_DEG_LAT
		cos_lat = math.cos(math.radians(place.lat))

		dlon = half / (KM_PER_DEG_LON * cos_lat)

		min_lon = place.lon - dlon
		min_lat = place.lat - dlat
		max_lon = place.lon + dlon
		max_lat = place.lat + dlat

		bbox = [min_lon, min_lat, max_lon, max_lat]

		return bbox
	except ValueError as e:
		print(f"Error computing bbox: {e}")
		return []


def _getbbox(place: Place) -> BBox:
	while True:
		aoi_size = input(
			f"Enter AOI size in Km (square side, minimum default value=[{DEFAULT_AOI_KM}Km]):",
			expected_type=float
		)
		
		size_km = float(aoi_size) if aoi_size else DEFAULT_AOI_KM

		if size_km <= 0:
			print("AOI size must be a positive number. Please try again.")
			continue
		if size_km < DEFAULT_AOI_KM:
			print(f"AOI size too small. Using default value of {DEFAULT_AOI_KM} Km.")
			size_km = DEFAULT_AOI_KM
		if size_km > 500:
			print("AOI size too large. Please enter a smaller value (max 500 Km).")
			continue

		coords = _compute_bbox(place, size_km)
		if not coords:
			print("Error computing bounding box. Please try again.")
			continue

		bbox = BBox(coords)
		return bbox


def getRegion(entry: LogEntry):
	geolocator = Nominatim(user_agent=USER_AGENT) # type: ignore[call-arg]

	while True:
		region_name = input("\nEnter the name of the region:")
		if len(region_name) == 1:
			print("Region name too short. Please enter a more specific name.")
			continue

		places = _requestRegionInfo(region_name, geolocator)
		if not places:
			continue

		_displayMatches(places, region_name)

		selectedPlace = _selectPlace(places)
		if selectedPlace is None:
			continue

		bbox = _getbbox(selectedPlace)
		if not bbox:
			print("Error getting bounding box.")
			break

		entry.place_query = region_name
		entry.place_name = selectedPlace.name
		entry.bbox = bbox.toList()

		break