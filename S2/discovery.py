import os
import re
from glob import glob


def extract_safe_timestamp(name):
    match = re.search(r"S2[AB]_MSIL2A_(\d{8}T\d{6})", name)
    return match.group(1) if match else ""


def _band_pair_key(path):
    name = os.path.basename(path)
    # Normalize B03/B08 filename token to match the same scene pair.
    key_name = re.sub(r"_B0[38]_10m\.jp2$", "_10m.jp2", name)
    return os.path.join(os.path.dirname(path), key_name)


def _discover_band_pairs_in_safe(safe_dir):
    b3_pattern = os.path.join(safe_dir, "GRANULE", "*", "IMG_DATA", "R10m", "*_B03_10m.jp2")
    b8_pattern = os.path.join(safe_dir, "GRANULE", "*", "IMG_DATA", "R10m", "*_B08_10m.jp2")

    b3_matches = sorted(glob(b3_pattern))
    b8_matches = sorted(glob(b8_pattern))

    b3_by_key = {_band_pair_key(path): path for path in b3_matches}
    b8_by_key = {_band_pair_key(path): path for path in b8_matches}

    common_keys = sorted(set(b3_by_key) & set(b8_by_key))
    pairs = []
    for key in common_keys:
        b3_path = b3_by_key[key]
        b8_path = b8_by_key[key]
        granule = os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(b3_path))))
        pairs.append(
            {
                "safe_dir": safe_dir,
                "safe_name": os.path.basename(safe_dir),
                "granule": granule,
                "b3": b3_path,
                "b8": b8_path,
            }
        )
    return pairs


def _discover_all_band_pairs(imagens_dir):
    safe_dirs = [p for p in glob(os.path.join(imagens_dir, "*.SAFE")) if os.path.isdir(p)]
    if not safe_dirs:
        raise FileNotFoundError(f"No .SAFE folders found in: {imagens_dir}")

    safe_dirs = sorted(safe_dirs, key=lambda path: extract_safe_timestamp(os.path.basename(path)))

    pairs = []
    for safe_dir in safe_dirs:
        pairs.extend(_discover_band_pairs_in_safe(safe_dir))

    if len(pairs) < 2:
        raise FileNotFoundError(
            "At least 2 B03/B08 10m pairs are required across .SAFE products in: "
            f"{imagens_dir}"
        )

    return pairs


def _extract_scene_date(pair):
    b3_name = os.path.basename(pair["b3"])
    match = re.search(r"_(\d{8})T\d{6}_B03_10m\.jp2$", b3_name)
    if not match:
        return "-"
    raw = match.group(1)
    return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"


def _compact_tail(path, parts=4):
    normalized = os.path.normpath(path)
    chunks = normalized.split(os.sep)
    if len(chunks) <= parts:
        return normalized
    return os.path.join("...", *chunks[-parts:])


def _list_band_pairs(pairs):
    print("\nAvailable band options (B03/B08 at 10m)")
    print("=" * 94)
    print(f"{'#':<4}{'Date':<12}{'Tile':<8}{'SAFE':<45}{'Granule'}")
    print("-" * 94)
    for idx, pair in enumerate(pairs, start=1):
        b3_name = os.path.basename(pair["b3"])
        tile = b3_name.split("_")[0] if "_" in b3_name else "-"
        date_label = _extract_scene_date(pair)
        safe_short = pair["safe_name"]
        if len(safe_short) > 42:
            safe_short = safe_short[:39] + "..."

        print(f"{idx:<4}{date_label:<12}{tile:<8}{safe_short:<45}{pair['granule']}")
        print(f"    B03: {_compact_tail(pair['b3'])}")
        print(f"    B08: {_compact_tail(pair['b8'])}")
        print("-" * 94)


def _ask_product_index(prompt, max_index):
    while True:
        raw = input(prompt).strip()
        if not raw:
            print("Please enter a number.")
            continue

        if not raw.isdigit():
            print("Invalid value. Please enter a valid number.")
            continue

        index = int(raw)
        if 1 <= index <= max_index:
            return index - 1

        print(f"Number out of range. Choose a value between 1 and {max_index}.")


def select_band_pairs(pairs):
    _list_band_pairs(pairs)

    before_idx = _ask_product_index("\nChoose BEFORE band number: ", len(pairs))
    while True:
        after_idx = _ask_product_index("Choose AFTER band number : ", len(pairs))
        if after_idx == before_idx:
            print("BEFORE and AFTER cannot be the same band option.")
            continue
        break

    return pairs[before_idx], pairs[after_idx]


def auto_find_band_paths(imagens_dir, interactive=True):
    pairs = _discover_all_band_pairs(imagens_dir)

    if interactive and os.isatty(0):
        before_pair, after_pair = select_band_pairs(pairs)
    else:
        before_pair, after_pair = pairs[0], pairs[-1]
        print("\nNon-interactive mode detected. Using first and last available band pairs.")

    b3_before = before_pair["b3"]
    b8_before = before_pair["b8"]
    b3_after = after_pair["b3"]
    b8_after = after_pair["b8"]

    print("\nSelected pairs:")
    print("Before:", before_pair["safe_name"], "|", before_pair["granule"])
    print("After :", after_pair["safe_name"], "|", after_pair["granule"])

    print("\nAuto-selected bands (10m):")
    print("B03 before:", b3_before)
    print("B08 before:", b8_before)
    print("B03 after :", b3_after)
    print("B08 after :", b8_after)

    return b3_before, b8_before, b3_after, b8_after
