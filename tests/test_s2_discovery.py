from datetime import datetime
from pathlib import Path

import pytest

from common.models import Product
from S2 import discovery
from S2.pclasses import Bands

def _make_pair(tile, safe_name, date_token):
    base = f"{tile}_{date_token}_B03_10m.jp2"
    return {
        "safe_dir": f"C:/Imagens/{safe_name}",
        "safe_name": safe_name,
        "granule": f"GRANULE_{safe_name}",
        "b3": f"C:/Imagens/{safe_name}/GRANULE/R10m/{base}",
        "b8": f"C:/Imagens/{safe_name}/GRANULE/R10m/{tile}_{date_token}_B08_10m.jp2",
    }


def _tile_from_path(path):
    return path.split("/")[-1].split("_")[0]


def _make_band(tile, safe_name, date_token):
    acquisition_date = datetime.strptime(date_token, "%Y%m%dT%H%M%S")
    product = Product(name=safe_name, path=Path(f"C:/Imagens/{safe_name}"), date=acquisition_date)
    base_dir = f"C:/Imagens/{safe_name}/GRANULE/R10m"
    return Bands(
        product=product,
        granule=f"GRANULE_{safe_name}",
        b3=f"{base_dir}/{tile}_{date_token}_B03_10m.jp2",
        b8=f"{base_dir}/{tile}_{date_token}_B08_10m.jp2",
        scl=f"C:/Imagens/{safe_name}/GRANULE/R20m/{tile}_{date_token}_SCL_20m.jp2",
    )


def test_auto_find_band_paths_noninteractive_uses_same_tile(monkeypatch):
    pairs = [
        _make_band("T36TVS", "scene_a.SAFE", "20230603T084559"),
        _make_band("T36TVS", "scene_b.SAFE", "20230618T084601"),
        _make_band("T36TWS", "scene_c.SAFE", "20230605T083601"),
        _make_band("T36TWS", "scene_d.SAFE", "20230618T084601"),
    ]

    monkeypatch.setattr(discovery, "discoverProducts", lambda entry: [object()])
    monkeypatch.setattr(discovery, "_extract_products_band_pairs", lambda products: pairs)

    bef, aft = discovery.discover_all_band_pairs({"place_query": "ignored"})

    assert _tile_from_path(bef.b3) == _tile_from_path(aft.b3)
    assert _tile_from_path(bef.b8) == _tile_from_path(aft.b8)
    assert "20230603T084559" in bef.b3
    assert "20230618T084601" in aft.b3


def test_auto_find_band_paths_falls_back_to_chronological_order(monkeypatch):
    pairs = [
        _make_band("T36TVS", "scene_a.SAFE", "20230603T084559"),
        _make_band("T36TWS", "scene_b.SAFE", "20230618T084601"),
        _make_band("T36UVS", "scene_c.SAFE", "20230609T153657"),
    ]

    monkeypatch.setattr(discovery, "discoverProducts", lambda entry: [object()])
    monkeypatch.setattr(discovery, "_extract_products_band_pairs", lambda products: pairs)

    bef, aft = discovery.discover_all_band_pairs({"place_query": "ignored"})

    assert bef.product.date == datetime(2023, 6, 3, 8, 45, 59)
    assert aft.product.date == datetime(2023, 6, 9, 15, 36, 57)


def test_auto_find_band_paths_raises_when_pairs_are_missing(monkeypatch):
    pair = _make_band("T36TVS", "scene_a.SAFE", "20230603T084559")

    monkeypatch.setattr(discovery, "discoverProducts", lambda entry: [object()])
    monkeypatch.setattr(discovery, "_extract_products_band_pairs", lambda products: [pair])

    with pytest.raises(FileNotFoundError):
        discovery.discover_all_band_pairs({"place_query": "ignored"})