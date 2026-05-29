from pathlib import Path

TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
SENTINEL_HUB_URL = "https://sh.dataspace.copernicus.eu/api/v1"
CATALOG_URL = f"{SENTINEL_HUB_URL}/catalog/1.0.0/search"
PROCESS_URL = f"{SENTINEL_HUB_URL}/process"

CATALOG_ODATA = "https://catalogue.dataspace.copernicus.eu/odata/v1"
ZIPPER_ODATA = "https://zipper.dataspace.copernicus.eu/odata/v1"
DOWNLOAD_ODATA = "https://download.dataspace.copernicus.eu/odata/v1"
FILTER_LIST_URL = f"{CATALOG_ODATA}/Products/OData.CSC.FilterList"

NOMINATIM_LANGUAGE = "en"
USER_AGENT = "SAR-MSI-FloodDetection"

DEFAULT_AOI_KM = 70.0
DEFAULT_DAYS_MARGIN = 5
DEFAULT_SEARCH_LIMIT = 10
DEFAULT_OUTPUT_RESOLUTION = 10

LOG_PATH = Path(__file__).resolve().parent / "search_log.csv"
EVAL_SCRIPTS_DIR = Path(__file__).resolve().parent / "evalScripts"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"
