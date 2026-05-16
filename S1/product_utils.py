import xml.etree.ElementTree as ET
from typing import Callable
from pathlib import Path
import re

def computeWorkflowVariables(
        dimstack_file: Path, 
        elevFunc: Callable[[Path, list[str]], float], 
        otsuVVFunc: Callable[[Path, str, str], float],
        otsuVHFunc: Callable[[Path, str, str], float],
    ) -> dict[str, str]:
    """Extract band variable names from a stacked DIMAP product."""

    with open(dimstack_file, "r", encoding="ISO-8859-1") as f:
        content = f.read()

    bands: list[str] = re.findall(r"<BAND_NAME>(.*?)</BAND_NAME>", content)

    vh_mst = vv_mst = vh_slv = vv_slv = elev_band = lc_band = ""
    for b in bands:
        if "VH_mst" in b:
            vh_mst = b
        elif "VV_mst" in b:
            vv_mst = b
        elif "VH_slv" in b:
            vh_slv = b
        elif "VV_slv" in b:
            vv_slv = b
        elif "elevation" in b.lower():
            elev_band = b
        elif "land_cover" in b.lower():
            lc_band = b

    if not all([vh_mst, vv_mst, vh_slv, vv_slv, elev_band, lc_band]):
        missing = [
            name
            for name, m in [
                ("Sigma0_VH_mst", vh_mst),
                ("Sigma0_VV_mst", vv_mst),
                ("Sigma0_VH_slv", vh_slv),
                ("Sigma0_VV_slv", vv_slv),
                ("Elevation band", elev_band),
                ("Land cover band", lc_band)
            ]
            if m == ""
        ]

        raise ValueError(
            "Could not extract all variable names from stack product.\n"
            f"Missing: {', '.join(missing)}\n"
            "Check that the stack was created correctly and band names are present."
        )

    vh_diff = f"10 * log10({vh_slv}) - 10 * log10({vh_mst})"
    vv_diff = f"10 * log10({vv_slv}) - 10 * log10({vv_mst})"

    hasDataAtPixel = (
        f"(({vh_slv} > 0 AND {vh_mst} > 0) AND ({vv_slv} > 0 AND {vv_mst} > 0))"
    )

    varsElevation = [elev_band, lc_band] 
    data_file = Path(str(dimstack_file).replace(".dim", ".data"))

    elev_threshold = elevFunc(data_file, varsElevation)
    otsu_vh = otsuVHFunc(data_file, vh_slv, vh_mst)
    otsu_vv = otsuVVFunc(data_file, vv_slv, vv_mst)

    variables = {
        "vh_diff": vh_diff,
        "vv_diff": vv_diff,
        "otsu_vh": otsu_vh,
        "otsu_vv": otsu_vv,
        "hasDataAtPixel": hasDataAtPixel,
        "elev_threshold": elev_threshold
    }

    # print(f"|\tVariables: ")
    # for k, v in variables.items():
    #     print(f"|\t- {k}: {v}")

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



def get_band_file(data_file: Path, band_name: str) -> Path:
    """Returns the .img file for a given band name from a SNAP .dim product."""
    img_file = data_file / f"{band_name}.img"

    if not img_file.exists():
        raise FileNotFoundError(
            f"Band '{band_name}' not found in {data_file}."
            f"Available bands: {list_bands(Path(str(data_file).replace('.data', '.dim')))}"
        )
    
    return img_file


def list_bands(dim_path: Path) -> list[str]:
    """Returns all band names present in a .dim product."""
    tree = ET.parse(str(dim_path))
    root = tree.getroot()
    return [
        el.text
        for el in root.findall(".//Spectral_Band_Info/BAND_NAME")
        if el.text
    ]
