from datetime import datetime
from pathlib import Path
import re

from .models import Product
from .paths import paths


def getProducts() -> list[Product]:
	print("Discovering products...")
	entries = list(paths["products"].iterdir())

	if not entries:
		raise FileNotFoundError(
			"No products found in data/.\n"
			"Please add at least two Sentinel-1 products (.SAFE or .zip) to the data/products/ directory."
		)

	valid_candidates: list[Path] = []

	for candidate in entries:
		is_safe = candidate.is_dir() and candidate.name.upper().endswith(".SAFE")
		is_zip = candidate.is_file() and candidate.suffix.lower() == ".zip"
		if is_safe or is_zip:
			valid_candidates.append(candidate)
		else:
			print(
				f"|\tInvalid product found in data/: {candidate.name}.\n"
				"|\tOnly .SAFE directories or .zip files are accepted. This entry will be ignored."
			)

	if len(valid_candidates) < 2:
		raise FileNotFoundError(
			"At least two Sentinel-1 products (.SAFE or .zip) "
			"are required in data/products/ folder."
		)

	# If there are more than two valid products, ask the user to select two.
	selected_candidates = choose_from_list(
		valid_candidates,
		select_count=2,
		prompt="More than two valid products found. Please select two to use:",
	)

	products: list[Product] = []
	for candidate in selected_candidates:
		acquisition_date = getDate(candidate)
		products.append(Product(name=candidate.name, path=candidate, date=acquisition_date))

	products.sort(key=lambda p: p.date)
	return products


def getDate(product: Path) -> datetime:
    match = re.search(r"_(\d{8}T\d{6})_", product.name)
    if not match:
        raise ValueError(f"Could not parse acquisition time from: {product.name}")

    result = datetime.strptime(match.group(1), "%Y%m%dT%H%M%S")
    print(f"|\tExtracted acquisition time: {result} from {product.name}")
    return result


def getProductFile(product: Path) -> Path:
    # If it's a .SAFE directory, return the manifest.safe file inside it
    if product.is_dir() and product.name.upper().endswith(".SAFE"):
        manifest = product / "manifest.safe"
        if not manifest.exists():
            raise FileNotFoundError(f"SAFE manifest not found: {manifest}")
        return manifest

    # If it's a .zip file, return it directly
    return product


def getShapeFile() -> Path:
    # Look for .shp files in the specified directory
    shape_files = sorted(paths["roi"].glob("**/*.shp"))

    if not shape_files:
        raise FileNotFoundError(
            "No .shp file found in data/region_of_interest/. "
            "Please add a shapefile to this directory."
        )

    if len(shape_files) > 1:
        selected = choose_from_list(
            shape_files,
            select_count=1,
            prompt="Multiple .shp files found in data/region_of_interest. Please select one:",
        )
        return selected[0]

    return shape_files[0]


def getFloodDimFile() -> Path:
    # Look for flood .dim files in the output directory
    dim_files = list(paths["out"].glob("flood_*.dim"))

    if not dim_files:
        raise FileNotFoundError(
            "No flood .dim product found in output directory.\n"
            "Run the flood mask step first."
        )

    return choose_from_list(
        dim_files, select_count=1, prompt="Multiple flood products found. Please select one:"
    )[0]


def getWorkflow(name: str) -> Path:
    workflow_path = Path(paths["workflows"] / name).with_suffix(".xml")
    if not workflow_path.exists():
        raise FileNotFoundError(f"Workflow XML not found: {workflow_path}")
    return workflow_path


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
