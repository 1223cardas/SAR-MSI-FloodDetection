from pathlib import Path
import json

from Acquisition.acquireProducts import acquireEntryFromLog
from .s1processing_config import S1_COLLECTION_NAME
from .utils import extractDateFromProduct, choose_from_list
from .pclasses import Product
from .paths import paths
from mainconfig import OUTPUT_DIR


def getEntry() -> dict:
	print("Discovering products...")
	csvEntry = acquireEntryFromLog(S1_COLLECTION_NAME)

	if csvEntry is None:
		raise FileNotFoundError(
			"No products found in data/.\n"
			"Please run the acquisition process first to create log entries."
	)

	return csvEntry.to_dict()


def discoverProducts(entry: dict) -> list[Product]:
	bef = Product(entry["beforeId"])
	aft = Product(entry["afterId"])

	products = [bef, aft]
	if not all(p.name for p in products):
		raise ValueError(
			"Both 'before' and 'after' product IDs must be present in the log entry. "
			"Please check the log and ensure both products are listed."
		)
	
	downloads = list(OUTPUT_DIR.iterdir())

	for p in products:
		p.date = extractDateFromProduct(p)
		for file in downloads:
			if file.name.startswith(p.name):
				p.path = file
	
	if not all(p.path is not None for p in products):
		raise FileNotFoundError(
			"Could not find both product files in the output directory. "
			"Please ensure the products are present and try again."
		)
	
	return products


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


def getFloodDataFile() -> Path:
	data_files = list(paths["out"].glob("*.data"))

	if not data_files:
		raise FileNotFoundError("No .dim files found in the output directory.")
	
	option = choose_from_list(
		data_files,
		select_count=1,
		prompt="Multiple .dim files found. Please select the one corresponding to the flood mask:"
	)

	return option[0]
