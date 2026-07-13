TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"

USER_AGENT = "SAR-MSI-FloodDetection"
NOMINATIM_LANGUAGE = "en"
DEFAULT_AOI_KM = 50.0
DEFAULT_DAYS_MARGIN = 5
DEFAULT_SEARCH_LIMIT = 20

SEARCH_DELTAS = [5, 10, 20]

# --- Orbit-aware "before" image selection ---

# Sentinel-1A repeats its ground track every 175 orbits (12 days). Two
# acquisitions only share look geometry (same relative orbit + pass
# direction) if they are spaced by a multiple of this cycle. Picking a
# "before" image on a different orbit introduces terrain-driven backscatter
# differences (layover/shadow/foreshortening) that swamp real flood signal,
# especially in hilly/mountainous AOIs.
S1_REPEAT_CYCLE_DAYS = 12

# How many repeat cycles back to search for an orbit-matched "before" image
# if none is found within the initial window.
MAX_BEFORE_REPEAT_CYCLES = 4

# Server-side cloud cover filter for Sentinel-2 (percent). Set to None to disable.
DEFAULT_S2_CLOUD_COVER = 80

SENTINELHUB_URL = "https://sh.dataspace.copernicus.eu/api/v1"
CATALOG_URL = f"{SENTINELHUB_URL}/catalog/1.0.0/search"

ODATA_DOWNLOAD_URL = "https://download.dataspace.copernicus.eu/odata/v1"
ODATA_CATALOG_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1"
FILTER_LIST_URL = f"{ODATA_CATALOG_URL}/Products/OData.CSC.FilterList"
ODATA_ZIPPER_URL = "https://zipper.dataspace.copernicus.eu/odata/v1"

KM_PER_DEG_LAT = 110.574
KM_PER_DEG_LON = 111.320

S1_COLLECTION = "sentinel-1-grd"
S2_COLLECTION = "sentinel-2-l2a"

CSV_FIELDNAMES = [
	"collection",
	"place_query",
	"place_name",
	"bbox",
	"crisis_date",
	"date_range",
	"beforeId",
	"afterId",
	"processed_at"
]


import builtins
CLI_PROMPT = "SAR-MSI-FloodDetection> "

def input(prompt: str = "", expected_type: type = str):
	print(prompt, end="\n")
	while True:
		user_input = builtins.input(CLI_PROMPT).strip()
		# print(f"User input: '{user_input}' (type: {type(user_input).__name__})")

		if not user_input: continue

		try:
			result = expected_type(user_input)
			# print(f"Parsed input: {result} (type: {type(result).__name__})")
			return result
		except ValueError:
			print(f"Invalid input. Expected a value of type {expected_type.__name__}. Please try again.")