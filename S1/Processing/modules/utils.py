from pathlib import Path


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


def displayResults(flood_count: float, px_area_m2: float, total_area_m2: float) -> None:
    print("\n--- Flood Calculation Results ---")
    print(f"Number of Flooded Pixels: {flood_count:,}")
    print(f"Estimated Pixel Size:     ~{px_area_m2:,.2f} m²")
    print(f"Total Flooded Area:       {total_area_m2:,.2f} m²  ({total_area_m2 / 1_000_000:.3f} km²)")