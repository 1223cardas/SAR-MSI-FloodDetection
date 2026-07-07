TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"

USER_AGENT = "SAR-MSI-FloodDetection"
NOMINATIM_LANGUAGE = "en"
DEFAULT_AOI_KM = 20.0
DEFAULT_DAYS_MARGIN = 5
DEFAULT_SEARCH_LIMIT = 20

# --- Orbit-aware "before" image selection ---
# Sentinel-1A repeats its ground track every 175 orbits (12 days). Two
# acquisitions only share look geometry (same relative orbit + pass
# direction) if they are spaced by a multiple of this cycle. Picking a
# "before" image on a different orbit introduces terrain-driven backscatter
# differences (layover/shadow/foreshortening) that swamp real flood signal,
# especially in hilly/mountainous AOIs.
S1_REPEAT_CYCLE_DAYS = 12

# Minimum gap (days) the "before" image must sit ahead of the crisis date.
# A reference image too close to the crisis date risks already showing
# early flood onset (slow-building floods) or pre-event weather effects.
MIN_BEFORE_BUFFER_DAYS = 0

# How many repeat cycles back to search for an orbit-matched "before" image
# if none is found within the initial window.
MAX_BEFORE_REPEAT_CYCLES = 4

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