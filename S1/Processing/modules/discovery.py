from S1.Processing.modules.s1processing_config import S1_COLLECTION_NAME
from S1.Processing.modules.utils import extractDateFromProduct
from S1.Processing.modules.pclasses import Product
from S1.Processing.modules.paths import paths
from Aquisition.aquireProducts import aquireEntryFromLog, aquireProducts
from mainconfig import OUTPUT_DIR
from pathlib import Path
import json


def getEntry() -> dict:
	print("Discovering products...")
	csvEntry = aquireEntryFromLog([S1_COLLECTION_NAME])

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

def choose_from_list(items: list[Path], select_count: int, prompt: str | None = None) -> list[Path]:
    """
    Prompt the user to select one or more items from a list of Path objects.
    Returns a list of the selected Path objects (length == select_count).
    """
    if not items:
        raise ValueError("No items available to select from.")

    if len(items) == select_count:
        return items

    if prompt:
        print(prompt)

    for i, item in enumerate(items, start=1):
        print(f"\t[{i}] {item.name}")

    while True:
        inp = input(
            f"Enter {select_count} number{'s' if select_count != 1 else ''} separated by a comma (e.g. 1{',2' if select_count>1 else ''}): "
        ).strip()
        parts = re.split(r"\s*,\s*", inp)

        if len(parts) != select_count:
            print(f"Please enter exactly {select_count} number{'s' if select_count != 1 else ''}.")
            continue

        try:
            idxs = [int(p) for p in parts]
        except ValueError:
            print("Invalid input. Use numbers like '1' or '1,2'.")
            continue

        if any(i not in range(1, len(items) + 1) for i in idxs):
            print("One or more numbers are out of range. Try again.")
            continue

        if len(set(idxs)) != len(idxs):
            print("Duplicate selection detected. Please choose distinct items.")
            continue

        return [items[i - 1] for i in idxs]
