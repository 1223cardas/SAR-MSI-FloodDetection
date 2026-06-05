import os
import re
from glob import glob

from Aquisition.aquireProducts import aquireEntryFromLog
from mainconfig import OUTPUT_DIR
from .pclasses import Product
from .config import S2_COLLECTION_NAME

def getEntry() -> dict:
	print("Discovering products...")
	csvEntry = aquireEntryFromLog([S2_COLLECTION_NAME])

	if csvEntry is None:
		raise FileNotFoundError(
			"No products found in data/.\n"
			"Please run the acquisition process first to create log entries."
	)

	return csvEntry.to_dict()

def extract_safe_timestamp(name):
    match = re.search(r"S2[AB]_MSIL2A_(\d{8}T\d{6})", name)
    return match.group(1) if match else ""

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
		p.date = extract_safe_timestamp(p.name)
		for file in downloads:
			if file.name.startswith(p.name):
				p.path = file
	
	if not all(p.path is not None for p in products):
		raise FileNotFoundError(
			"Could not find both product files in the output directory. "
			"Please ensure the products are present and try again."
		)
	
	return products


def _band_pair_key(path):
    name = os.path.basename(path)
    # Normaliza os tokens de banda e resolução para dar match no mesmo par de cena.
    key_name = re.sub(r"_(B0[38]_10m|SCL_20m)\.jp2$", "_normalized.jp2", name)
    return key_name


def _discover_band_pairs_in_safe(product_dir):
    # Padrões de busca para B03, B08 (10m) e SCL (20m)
    b3_pattern = os.path.join(product_dir, "GRANULE", "*", "IMG_DATA", "R10m", "*_B03_10m.jp2")
    b8_pattern = os.path.join(product_dir, "GRANULE", "*", "IMG_DATA", "R10m", "*_B08_10m.jp2")
    scl_pattern = os.path.join(product_dir, "GRANULE", "*", "IMG_DATA", "R20m", "*_SCL_20m.jp2")

    b3_matches = sorted(glob(b3_pattern))
    b8_matches = sorted(glob(b8_pattern))
    scl_matches = sorted(glob(scl_pattern))

    b3_by_key = {_band_pair_key(path): path for path in b3_matches}
    b8_by_key = {_band_pair_key(path): path for path in b8_matches}
    scl_by_key = {_band_pair_key(path): path for path in scl_matches}

    # Garante que a chave existe nos três dicionários
    common_keys = sorted(set(b3_by_key) & set(b8_by_key) & set(scl_by_key))
    pairs = []
    
    for key in common_keys:
        b3_path = b3_by_key[key]
        b8_path = b8_by_key[key]
        scl_path = scl_by_key[key]
        
        granule = os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(b3_path))))
        pairs.append(
            {
                "safe_dir": product_dir,
                "safe_name": os.path.basename(product_dir),
                "granule": granule,
                "b3": b3_path,
                "b8": b8_path,
                "scl": scl_path,
            }
        )
    return pairs


def discover_all_band_pairs(imagens_dir):
    entry = getEntry()
    products = discoverProducts(entry)

    pairs = []
    for product_dir in products:
        pairs.extend(_discover_band_pairs_in_safe(product_dir.path))

    if len(pairs) < 2:
        raise FileNotFoundError(
            "Pelo menos 2 pares de bandas B03/B08/SCL são necessários nos produtos .SAFE em: "
            f"{imagens_dir}"
        )

    before_pair, after_pair = pairs

    b3_before = before_pair["b3"]
    b8_before = before_pair["b8"]
    scl_before = before_pair["scl"]
    
    b3_after = after_pair["b3"]
    b8_after = after_pair["b8"]
    scl_after = after_pair["scl"]

    print("\nSelected pairs:")
    print("Before:", before_pair["safe_name"], "|", before_pair["granule"])
    print("After :", after_pair["safe_name"], "|", after_pair["granule"])

    print("\nAuto-selected bands:")
    print("B03 before :", b3_before)
    print("B08 before :", b8_before)
    print("SCL before (20m):", scl_before)
    print("B03 after  :", b3_after)
    print("B08 after  :", b8_after)
    print("SCL after (20m) :", scl_after)

    return b3_before, b8_before, scl_before, b3_after, b8_after, scl_after