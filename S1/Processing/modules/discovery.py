from pathlib import Path
import json

from Acquisition.acquireProducts import discoverProducts as shared_discoverProducts
from Acquisition.acquireProducts import getEntry as shared_getEntry
from .s1processing_config import S1_COLLECTION_NAME
from .paths import paths

from common import Product

def getEntry() -> dict:
	return shared_getEntry(S1_COLLECTION_NAME)


def discoverProducts(entry: dict) -> list[Product]:
	return shared_discoverProducts(entry)


def discoverAOI(entry: dict) -> str:
	bbox = entry.get("bbox")

	if isinstance(bbox, str):
		try:
			bbox = json.loads(bbox)
		except Exception:
			raise ValueError("Entry 'bbox' is a string but not valid JSON list")

	if not isinstance(bbox, list) or len(bbox) != 4:
		raise ValueError(
			"Entry 'bbox' must be a list of four floats: [min_lon, min_lat, max_lon, max_lat]"
		)

	min_lon, min_lat, max_lon, max_lat = bbox

	return (
        f"POLYGON (({min_lon} {min_lat}, "
        f"{max_lon} {min_lat}, "
        f"{max_lon} {max_lat}, "
        f"{min_lon} {max_lat}, "
        f"{min_lon} {min_lat}))"
    )


def getWorkflow(name: str) -> Path:
	workflow_path = paths["workflows"] / f"{name}.xml"
	if not workflow_path.exists():
		raise FileNotFoundError(f"Workflow XML not found: {workflow_path}")
	return workflow_path


def getProductFile(product: Path) -> Path:
    # If it's a .SAFE directory, return the manifest.safe file inside it
	if product.is_dir() and product.name.upper().endswith(".SAFE"):
		# print(f"Product {product.name} is a .SAFE directory. Looking for manifest.safe inside it.")
		manifest = product / "manifest.safe"
		if not manifest.exists():
			raise FileNotFoundError(f"SAFE manifest not found: {manifest}")
		return manifest

	# print(f"Product {product.name} is not a .SAFE directory. Using the file directly.")
	# If it's a .zip file, return it directly
	return product
