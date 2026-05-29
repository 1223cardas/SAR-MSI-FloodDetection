from datetime import datetime, timezone
from geopy.geocoders import Nominatim
from classes import Place
from config import NOMINATIM_LANGUAGE, USER_AGENT

def getInput(prompt: str, errorMessage: str, expectedType):
	while True:
		user_input = input(prompt).strip()
		try:
			return expectedType(user_input)
		except ValueError:
			print(errorMessage)


def geocode_place(limit: int = 5) -> tuple[str, list[Place]]:
	geolocator = Nominatim(user_agent=USER_AGENT, timeout=20) # type: ignore[call-arg]
	while True:
		query = getInput(
				"Enter the name of the region: ",
				"Invalid input. Please enter a valid place name.",
				str
			)
		if not query:
			print("Input cannot be empty. Please try again.")
			continue

		try:
			locations = geolocator.geocode(
				query,
				exactly_one=False,
				limit=limit,
				language=NOMINATIM_LANGUAGE, # type: ignore[call-arg]
			)

			if not locations or locations is None:
				print(
					f"No geocoding results found for {query}. "
					f"Try a different name."
				)
				continue

		except Exception as e:
			print("Geocoding request failed:", str(e))

		places = []
		for loc in locations: # type: ignore[call-arg]
			raw: dict = loc.raw
			display_name = raw.get("display_name") or "N/A"

			places.append(Place(display_name, loc.latitude, loc.longitude))
		return query, places


def chooseRegion() -> tuple[str, Place]:
	query, places = geocode_place()

	while True:
		print(f"Matches with {query}:")
		for idx, place in enumerate(places, start=1):
			print(f"\t[{idx}] {place.name} (lat={place.lat}, lon={place.lon})")

		choice = getInput(
			"Select a result number or press Enter to search again: ",
			"Invalid selection. Use a number from the list.",
			int
		)
		if not choice:
			continue

		if choice < 1 or choice > len(places):
			print("Selection out of range.")
			continue

		place = places[choice - 1]
		confirm = input(f"Use '{place.name}'? [y/n]: ").strip().lower()
		if confirm in ("y", "yes"):
			return query, place



def prompt_numeric(prompt: str, default):
	while True:
		raw = input(f"{prompt}: ").strip()
		if not raw:
			return default

		try:
			value = type(default)(raw)
			if value <= 0:
				print("Value must be greater than zero.")
				continue
			print(f"Returning value: {value}")
			return value
		except (ValueError, TypeError):
			print("Invalid input. Try again.")



def prompt_crisis_date() -> str:
	while True:
		raw = input("Crisis date (YYYY-MM-DD or YYYY-MM-DD-hh, Enter = today): ").strip()

		if not raw:
			dt = datetime.now(timezone.utc).replace(tzinfo=None)
			return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

		# Try parsing with hour first: YYYY-MM-DD-HH
		try:
			d = datetime.strptime(raw, "%Y-%m-%d-%H")
			# set minutes and seconds to 59 to include the whole hour
			return datetime(d.year, d.month, d.day, d.hour, 59, 59).strftime("%Y-%m-%dT%H:%M:%SZ")
		except ValueError:
			# Try parsing date-only: YYYY-MM-DD
			try:
				d = datetime.strptime(raw, "%Y-%m-%d")
				return datetime(d.year, d.month, d.day, 12, 59, 59).strftime("%Y-%m-%dT%H:%M:%SZ")
			except ValueError:
				print("Invalid date format. Use YYYY-MM-DD or YYYY-MM-DD-hh.")