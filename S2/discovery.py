from pathlib import Path
import re

from Acquisition.acquireProducts import discoverProducts as shared_discoverProducts
from Acquisition.acquireProducts import getEntry as shared_getEntry
from common import checkEntryInOutput as shared_checkEntryInOutput

from .pclasses import Bands, Product
from .config import OUT_DIR

from common import S2_COLLECTION

def getEntry() -> dict:
	return shared_getEntry(S2_COLLECTION)


def discoverProducts(entry: dict) -> list[Product]:
	return shared_discoverProducts(entry)


def build_output_file(base_name: str) -> Path:
	return OUT_DIR / base_name


def checkEntryInOutput(entry: dict) -> tuple[str, str, Path | None]:
	return shared_checkEntryInOutput(entry, build_output_func=build_output_file)


# ---------------------------------------------------------------------------
# Band-pair discovery
# ---------------------------------------------------------------------------

def _band_pair_key(path: Path) -> str:
	"""Normalize band/resolution tokens so before and after acquisitions align."""
	return re.sub(r"_(B0[38]_10m|SCL_20m)\.jp2$", "_normalized.jp2", path.name)


def _discover_band_pairs_in_safe(product_dir: Path) -> list[Bands]:
	"""Scan a .SAFE directory and return all matching B03/B08/SCL triplets."""
	product_path = Path(product_dir)

	scl_matches = sorted(product_path.rglob("GRANULE/*/IMG_DATA/R20m/*_SCL_20m.jp2"))
	b3_matches = sorted(product_path.rglob("GRANULE/*/IMG_DATA/R10m/*_B03_10m.jp2"))
	b8_matches = sorted(product_path.rglob("GRANULE/*/IMG_DATA/R10m/*_B08_10m.jp2"))

	scl_by_key = {_band_pair_key(p): p for p in scl_matches}
	b3_by_key  = {_band_pair_key(p): p for p in b3_matches}
	b8_by_key  = {_band_pair_key(p): p for p in b8_matches}

	common_keys = b3_by_key.keys() & b8_by_key.keys() & scl_by_key.keys()

	product = Product(name=product_path.name, path=product_path)
	try:
		product.extractDateFromProduct()
	except ValueError:
		pass

	bands_list = []
	for k in sorted(common_keys):
		b3 = b3_by_key[k]
		bands_list.append(
			Bands(
				product=product,
				granule=b3.parents[3].name,
				b3=str(b3),
				b8=str(b8_by_key[k]),
				scl=str(scl_by_key[k]),
			)
		)
	return bands_list


def _extract_products_band_pairs(products: list[Product]) -> list[Bands]:
	"""Aggregate band pairs across all products."""
	return [pair for p in products for pair in _discover_band_pairs_in_safe(p.path)]


def _tile_from_b3(b3_path: str) -> str:
	"""Extract the MGRS tile code from a band filename."""
	name = Path(b3_path).name
	return name.split("_")[0] if "_" in name else ""


def discover_all_band_pairs(entry: dict | None = None) -> tuple[Bands, Bands]:
	"""
	Auto-detect the before/after band pair for the given entry.
	Returns (before, after) sorted chronologically.
	"""
	target_entry = entry if entry is not None else getEntry()
	products = discoverProducts(target_entry)
	pairs    = _extract_products_band_pairs(products)

	if len(pairs) < 2:
		raise FileNotFoundError("At least 2 B03/B08/SCL band pairs are required in .SAFE")

	by_tile: dict[str, list[Bands]] = {}
	for p in pairs:
		by_tile.setdefault(_tile_from_b3(p.b3), []).append(p)

	candidate_tiles = [t for t, vals in by_tile.items() if t and len(vals) >= 2]

	if candidate_tiles:
		selected = sorted(by_tile[sorted(candidate_tiles)[0]], key=lambda x: x.product.date)
		before, after = selected[0], selected[-1]
	else:
		selected = sorted(pairs, key=lambda x: x.product.date)
		before, after = selected[0], selected[1]

	print("\n[INFO] Auto-selected band context pairs:")
	print(f"|\tB03 Before : {before.b3}")
	print(f"|\tB08 Before : {before.b8}")
	print(f"|\tSCL Before : {before.scl} (20m)")
	print(f"|\tB03 After  : {after.b3}")
	print(f"|\tB08 After  : {after.b8}")
	print(f"|\tSCL After  : {after.scl} (20m)")

	return before, after