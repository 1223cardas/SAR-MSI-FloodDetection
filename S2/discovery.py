from Acquisition.acquireProducts import discoverProducts as shared_discoverProducts
from Acquisition.acquireProducts import getEntry as shared_getEntry
from .config import S2_COLLECTION_NAME
from .pclasses import Product, Bands

from pathlib import Path
import re


def getEntry() -> dict:
	return shared_getEntry(S2_COLLECTION_NAME)


def discoverProducts(entry: dict) -> list[Product]:
	return shared_discoverProducts(entry)


def _band_pair_key(path) -> str:
    """Normalize band and resolution tokens to align matching tile captures."""
    return re.sub(r"_(B0[38]_10m|SCL_20m)\.jp2$", "_normalized.jp2", path.name)


def _discover_band_pairs_in_safe(product_dir: Path) -> list[Bands]:
    """Scan an individual .SAFE architecture directory to identify matching band triplets."""
    product_path = Path(product_dir)
    
    # Locate bands dynamically under the granule structure using pathlib globbing
    b3_matches = sorted(product_path.rglob("GRANULE/*/IMG_DATA/R10m/*_B03_10m.jp2"))
    b8_matches = sorted(product_path.rglob("GRANULE/*/IMG_DATA/R10m/*_B08_10m.jp2"))
    scl_matches = sorted(product_path.rglob("GRANULE/*/IMG_DATA/R20m/*_SCL_20m.jp2"))

    b3_by_key = {_band_pair_key(p): p for p in b3_matches}
    b8_by_key = {_band_pair_key(p): p for p in b8_matches}
    scl_by_key = {_band_pair_key(p): p for p in scl_matches}

    common_keys = b3_by_key.keys() & b8_by_key.keys() & scl_by_key.keys()

    product = Product(name=product_path.name, path=product_path)
    try:
        product.extractDateFromProduct()
    except ValueError:
        pass  # Fallback to datetime.min if pattern parsing fails

    bands_list = []
    for k in sorted(common_keys):
        b3 = b3_by_key[k]
        granule = b3.parents[3].name  # Extracts the unique Granule folder name safely

        bands_list.append(
            Bands(
                product=product,
                granule=granule,
                b3=str(b3),
                b8=str(b8_by_key[k]),
                scl=str(scl_by_key[k]),
            )
        )

    return bands_list


def _extract_products_band_pairs(products: list[Product]) -> list[Bands]:
    """Extract and aggregate all historical band pairs across verified products."""
    pairs = []
    for p in products:
        pairs.extend(_discover_band_pairs_in_safe(p.path))
    return pairs


def _tile_from_b3(b3_path: str) -> str:
    """Extract target MGRS tile code identifier out of a band file name."""
    name = Path(b3_path).name
    return name.split("_")[0] if "_" in name else ""


def discover_all_band_pairs(entry: dict | None = None) -> tuple[Bands, Bands]:
    """
    Auto-detect target scene acquisitions tracking continuous changes between periods.
    Returns a tuple containing the (before, after) structured asset layers.
    """
    target_entry = entry if entry is not None else getEntry()
    products = discoverProducts(target_entry)
    
    pairs = _extract_products_band_pairs(products)

    if len(pairs) < 2:
        raise FileNotFoundError(
            f"At least 2 baseline B03/B08/SCL band pairs are required in .SAFE"
        )

    # Group paired records using localized geographic tiles
    by_tile: dict[str, list[Bands]] = {}
    for p in pairs:
        tile = _tile_from_b3(p.b3)
        by_tile.setdefault(tile, []).append(p)

    # Filter tiles that have enough acquisitions to build a time-series pair
    candidate_tiles = [t for t, vals in by_tile.items() if t and len(vals) >= 2]
    
    if candidate_tiles:
        chosen_tile = sorted(candidate_tiles)[0]
        # Sort based on the verified datetime parsed within Product classes
        selected = sorted(by_tile[chosen_tile], key=lambda x: x.product.date)
        before, after = selected[0], selected[-1]
    else:
        # Fallback sorting over general stack acquisitions if no dual matches share a single tile
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