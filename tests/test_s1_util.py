from pathlib import Path
from datetime import datetime

import pytest

from S1 import utilS1


def test_getDate_parses_safe_name():
    name = "S1A_IW_GRDH_1SDV_20230606T040507_20230606T040532_048860_05E039_08B2.SAFE"
    dt = utilS1.getDate(Path(name))
    assert isinstance(dt, datetime)
    assert dt == datetime(2023, 6, 6, 4, 5, 7)


def test_getDate_raises_on_invalid_name():
    with pytest.raises(ValueError):
        utilS1.getDate(Path("invalid_product_name.SAFE"))


def test_getProductFile_for_safe_dir(tmp_path):
    safe = tmp_path / "TEST.SAFE"
    safe.mkdir()
    manifest = safe / "manifest.safe"
    manifest.write_text("manifest")

    result = utilS1.getProductFile(safe)
    assert result == manifest


def test_getProductFile_for_zip(tmp_path):
    z = tmp_path / "product.zip"
    z.write_text("zipdata")

    result = utilS1.getProductFile(z)
    assert result == z


def test_getProductFile_missing_manifest(tmp_path):
    safe = tmp_path / "NO_MANIFEST.SAFE"
    safe.mkdir()
    with pytest.raises(FileNotFoundError):
        utilS1.getProductFile(safe)
