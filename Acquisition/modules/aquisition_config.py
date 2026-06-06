TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"

USER_AGENT = "SAR-MSI-FloodDetection"
NOMINATIM_LANGUAGE = "en"
DEFAULT_AOI_KM = 20.0
DEFAULT_DAYS_MARGIN = 5
DEFAULT_SEARCH_LIMIT = 20

SENTINELHUB_URL = "https://sh.dataspace.copernicus.eu/api/v1"
CATALOG_URL = f"{SENTINELHUB_URL}/catalog/1.0.0/search"

ODATA_DOWNLOAD_URL = "https://download.dataspace.copernicus.eu/odata/v1"
ODATA_CATALOG_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1"
FILTER_LIST_URL = f"{ODATA_CATALOG_URL}/Products/OData.CSC.FilterList"
ODATA_ZIPPER_URL = "https://zipper.dataspace.copernicus.eu/odata/v1"

KM_PER_DEG_LAT = 110.574
KM_PER_DEG_LON = 111.320

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
