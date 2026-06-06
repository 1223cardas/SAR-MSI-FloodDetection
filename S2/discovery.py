import os
import re
from pathlib import Path
from glob import glob

from Acquisition.acquireProducts import acquireEntryFromLog
from mainconfig import OUTPUT_DIR
from .pclasses import Product, Bands
from .config import S2_COLLECTION_NAME


def getEntry() -> dict:
	print("Discovering products...")
	csvEntry = acquireEntryFromLog(S2_COLLECTION_NAME)

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
        for file in downloads:
            if file.name.startswith(p.name):
                p.path = file
	
    if not all(p.path is not None for p in products):
        raise FileNotFoundError(
            "Could not find both product files in the output directory. "
            "Please ensure the products are present and try again."
        )

    return products


def _band_pair_key(path) -> str:
    name = os.path.basename(path)
    # Normaliza os tokens de banda e resolução para dar match no mesmo par de cena.
    key_name = re.sub(r"_(B0[38]_10m|SCL_20m)\.jp2$", "_normalized.jp2", name)
    return key_name


def _discover_band_pairs_in_safe(product_dir: Path) -> list[Bands]:
    product_dir = Path(product_dir)

    b3_pattern = os.path.join(product_dir, "GRANULE", "*", "IMG_DATA", "R10m", "*_B03_10m.jp2")
    b8_pattern = os.path.join(product_dir, "GRANULE", "*", "IMG_DATA", "R10m", "*_B08_10m.jp2")
    scl_pattern = os.path.join(product_dir, "GRANULE", "*", "IMG_DATA", "R20m", "*_SCL_20m.jp2")

    b3_matches = sorted(glob(b3_pattern))
    b8_matches = sorted(glob(b8_pattern))
    scl_matches = sorted(glob(scl_pattern))

    b3_by_key = {_band_pair_key(p): p for p in b3_matches}
    b8_by_key = {_band_pair_key(p): p for p in b8_matches}
    scl_by_key = {_band_pair_key(p): p for p in scl_matches}

    common_keys = b3_by_key.keys() & b8_by_key.keys() & scl_by_key.keys()

    product = Product(
        name=product_dir.name,
        path=product_dir
    )

    bands = []
    for k in sorted(common_keys):
        b3 = b3_by_key[k]
        b8 = b8_by_key[k]
        scl = scl_by_key[k]
        granule = Path(b3).parents[3].name

        bands.append(
            Bands(
                product=product,
                granule=granule,
                b3=str(b3),
                b8=str(b8),
                scl=str(scl),
            )
        )

    return bands


def discover_all_band_pairs(imagens_dir) -> tuple[Bands, Bands]:
    entry = getEntry()
    products = discoverProducts(entry)
	
    pairs: list[Bands] = []
    for product_dir in products:
        pairs.extend(_discover_band_pairs_in_safe(product_dir.path))
	
    if len(pairs) < 2:
        raise FileNotFoundError(
            "Pelo menos 2 pares de bandas B03/B08/SCL são necessários nos produtos .SAFE em: "
            f"{imagens_dir}"
        )
	
    before, after = pairs

    print("\nAuto-selected bands:")
    print("B03 before :", before.b3)
    print("B08 before :", before.b8)
    print("SCL before (20m):", before.scl)
    print("B03 after  :", after.b3)
    print("B08 after  :", after.b8)
    print("SCL after (20m) :", after.scl)

    return before, after