import xml.etree.ElementTree as ET
from pathlib import Path
import re


def computeWorkflowVariables(dimstack_file: Path) -> dict[str, str]:
    """Extract band variable names from a stacked DIMAP product."""
    print(f"Reading stack variables from: {dimstack_file}")

    with open(dimstack_file, "r", encoding="ISO-8859-1") as f:
        content = f.read()

    date_pattern = r"(\d{8}|\d{2}[A-Za-z]{3}\d{4})"

    vh_mst_match = re.search(rf"Sigma0_VH_mst_{date_pattern}", content)
    vv_mst_match = re.search(rf"Sigma0_VV_mst_{date_pattern}", content)
    vh_slv_match = re.search(rf"Sigma0_VH_slv\d+_{date_pattern}", content)
    vv_slv_match = re.search(rf"Sigma0_VV_slv\d+_{date_pattern}", content)

    if not all([vh_mst_match, vv_mst_match, vh_slv_match, vv_slv_match]):
        missing = [
            name
            for name, m in [
                ("Sigma0_VH_mst", vh_mst_match),
                ("Sigma0_VV_mst", vv_mst_match),
                ("Sigma0_VH_slv", vh_slv_match),
                ("Sigma0_VV_slv", vv_slv_match),
            ]
            if m is None
        ]
        raise ValueError(
            "Could not extract all variable names from stack product.\n"
            f"Missing: {', '.join(missing)}\n"
            "Check that the stack was created correctly and band names are present."
        )

    vh_mst = vh_mst_match.group(0)  # type: ignore[union-attr]
    vv_mst = vv_mst_match.group(0)  # type: ignore[union-attr]
    vh_slv = vh_slv_match.group(0)  # type: ignore[union-attr]
    vv_slv = vv_slv_match.group(0)  # type: ignore[union-attr]

    vh_diff = f"10 * log10({vh_slv}) - 10 * log10({vh_mst})"
    vv_diff = f"10 * log10({vv_slv}) - 10 * log10({vv_mst})"

    variables = {
        "vh_mst": vh_mst,
        "vv_mst": vv_mst,
        "vh_slv": vh_slv,
        "vv_slv": vv_slv,
        "vh_diff": vh_diff,
        "vv_diff": vv_diff,
    }

    return variables


def refactor_snap_product(full_path: str | Path) -> None:
    """
    Renames a SNAP DIMAP product from 'name_PROCESSING' to 'name',
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

    print(f"Refactored: '{full_name}' -> '{new_name}'")


def get_band_file(dim_path: Path, band_name: str) -> Path:
    """
    Parses a SNAP .dim file to find the .img file path for a given band name.
    The .data folder sits next to the .dim file.
    """
    tree = ET.parse(dim_path)
    root = tree.getroot()

    # Band names and their data files are listed under <Image_Interpretation>
    for spectral_band in root.findall(".//Spectral_Band_Info"):
        name_el = spectral_band.find("BAND_NAME")
        if name_el is not None and name_el.text == band_name:
            # The index of this band maps to the .img file in the .data folder
            # Files are named like: <product>.data/<band_name>.img
            data_dir = dim_path.parent / (dim_path.stem + ".data")
            img_file = data_dir / f"{band_name}.img"
            if img_file.exists():
                return img_file
            # Sometimes SNAP uses the band index as filename fallback
            band_index_el = spectral_band.find("BAND_INDEX")
            if band_index_el is not None:
                img_file = data_dir / f"band_{band_index_el.text}.img"
                if img_file.exists():
                    return img_file

    raise FileNotFoundError(
        f"Band '{band_name}' not found in {dim_path}. "
        f"Available bands: {list_bands(dim_path)}"
    )


def list_bands(dim_path: Path) -> list[str]:
    """Returns all band names present in a .dim product."""
    tree = ET.parse(str(dim_path))
    root = tree.getroot()
    return [
        el.text
        for el in root.findall(".//Spectral_Band_Info/BAND_NAME")
        if el.text
    ]
