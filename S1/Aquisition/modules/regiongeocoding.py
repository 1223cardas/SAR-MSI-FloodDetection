from geopy.geocoders import Nominatim
from .classes import Place, BBox, LogEntry
from . import config
import math

def requestRegionInfo(region_name: str, geolocator: Nominatim) -> list[Place]:
	try:
		print(f"Requesting geocoding info for '{region_name}'...")
		locations = geolocator.geocode(
			region_name,
			exactly_one=False,
			limit=config.DEFAULT_SEARCH_LIMIT,
			language=config.NOMINATIM_LANGUAGE # type: ignore[call-arg]
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



def selectPlace(places: list[Place]) -> Place | None:
	while True:
		selection = input(
			"Select a region by entering the corresponding number.\n"
			"(Press Enter to check another region):\n" + config.CLI_PROMPT
		)
		if not selection: break

		try:
			selected_index = int(selection) - 1
			if selected_index not in range(1, len(places) + 1):
				print("Selection out of range. Please enter a valid number.")
				continue
			
			place = places[selected_index]
		except ValueError:
			print("Invalid input. Please enter a number.")

		confirm = input(
			f"Use '{place.name}'? [y/n]\n"
			"(Press Enter to choose another region):\n" + config.CLI_PROMPT
		).strip().lower()
		if confirm not in ("y", "yes"): continue

		return place
	
	return None



def getbbox(place: Place) -> BBox:
	while True:
		aoi_size = input(
			f"Enter AOI size in Km (square side, Press Enter for default value [{config.DEFAULT_AOI_KM}Km]): "
		).strip()

		size_km = float(aoi_size) if aoi_size else config.DEFAULT_AOI_KM

		coords = compute_bbox(place, size_km)
		if not coords:
			print("Error computing bounding box. Please try again.")
			continue
		
		bbox = BBox(coords)
		return bbox



def compute_bbox(place: Place, size_km: float) -> list[float]:
	try:
		half = size_km / 2.0
		dlat = half / config.KM_PER_DEG_LAT
		cos_lat = math.cos(math.radians(place.lat))

		dlon = half / (config.KM_PER_DEG_LON * cos_lat)

		min_lon = place.lon - dlon
		min_lat = place.lat - dlat
		max_lon = place.lon + dlon
		max_lat = place.lat + dlat

		bbox = [min_lon, min_lat, max_lon, max_lat]

		return bbox
	except ValueError as e:
		print(f"Error computing bbox: {e}")
		return []



def getRegion(entry: LogEntry):
	geolocator = Nominatim(user_agent=config.USER_AGENT) # type: ignore[call-arg]

	while True:
		region_name = input(
			
			"\nEnter the name of the region:\n" + config.CLI_PROMPT
		).strip()
		if not region_name:
			print("Input cannot be empty. Please try again.")
			continue
		
		places = requestRegionInfo(region_name, geolocator)
		if not places:
			continue

		print(f"Matches with {region_name}:")
		for idx, place in enumerate(places, start=1):
			print(f"\t[{idx}] {place.name} (lat={place.lat}, lon={place.lon})")
		print()
		
		
		selectedPlace = selectPlace(places)
		# if user wants to check another region, selectedPlace will be None,
		# so we can just continue the loop and ask for another region name
		if selectedPlace is None:
			continue

		bbox = getbbox(selectedPlace)
		if not bbox:
			print("Error getting bounding box.")
			break

		entry.place_query = region_name
		entry.place_name = place.name
		entry.bbox = bbox.toList()
		
		break