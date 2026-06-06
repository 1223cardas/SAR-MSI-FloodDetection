import re
from pathlib import Path
from datetime import datetime
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