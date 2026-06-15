import re
from pathlib import Path
from datetime import datetime
import xml.etree.ElementTree as ET

from .pclasses import Product


def extractDateFromProduct(product: Product) -> datetime:
	# Assuming the product name format is something like "S1A_IW_GRDH_1SDV_20210101T123456_20210101T123456_012345_67890_ABCDE.SAFE"
	# The date is usually in the format YYYYMMDDTHHMMSS
	match = re.search(r"_(\d{8}T\d{6})_", product.name)
	if not match:
		raise ValueError(f"Could not parse acquisition time from: {product.name}")

	result = datetime.strptime(match.group(1), "%Y%m%dT%H%M%S")
	# print(f"|\tExtracted acquisition time: {result} from {product.name}")
	return result



def refactor_snap_product(full_path: str | Path) -> None:
    """
    Rename a SNAP DIMAP product from 'name_PROCESSING' to 'name',
    updating the .dim file contents and renaming the .data folder.
    """
    full_path = Path(full_path)
    folder = full_path.parent
    full_name = full_path.name
    new_name = full_name.replace("_PROCESSING", "")

    dim_old = folder / f"{full_name}.dim"
    dim_new = folder / f"{new_name}.dim"
    data_old = folder / f"{full_name}.data"
    data_new = folder / f"{new_name}.data"

    content = dim_old.read_text(encoding="ISO-8859-1")
    content = content.replace(full_name, new_name)
    dim_old.write_text(content, encoding="ISO-8859-1")

    dim_old.rename(dim_new)

    if data_old.is_dir():
        data_old.rename(data_new)
    else:
        print(f"Warning: '{data_old}' folder not found, skipping.")

    # print(f"Refactored: '{full_name}' -> '{new_name}'")


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


def get_band_file(data_file: Path, band_name: str) -> Path:
    """Return the .img file for a given band name from a SNAP .dim product."""
    img_file = data_file / f"{band_name}.img"

    if not img_file.exists():
        raise FileNotFoundError(
            f"Band '{band_name}' not found in {data_file}."
            f"Available bands: {list_bands(Path(str(data_file).replace('.data', '.dim')))}"
        )

    return img_file


def list_bands(dim_path: Path) -> list[str]:
    """Return all band names present in a .dim product."""
    tree = ET.parse(str(dim_path))
    root = tree.getroot()
    return [
        el.text
        for el in root.findall(".//Spectral_Band_Info/BAND_NAME")
        if el.text
    ]
