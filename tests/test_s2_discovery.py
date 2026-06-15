from S2 import discovery

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


def test_auto_find_band_paths_noninteractive_uses_same_tile(monkeypatch):
    pairs = [
        _make_pair("T36TVS", "scene_a.SAFE", "20230603T084559"),
        _make_pair("T36TVS", "scene_b.SAFE", "20230618T084601"),
        _make_pair("T36TWS", "scene_c.SAFE", "20230605T083601"),
        _make_pair("T36TWS", "scene_d.SAFE", "20230618T084601"),
    ]

    monkeypatch.setattr(discovery, "_discover_all_band_pairs", lambda imagens_dir: pairs)
    monkeypatch.setattr(discovery.os, "isatty", lambda fd: False)

    bef, aft = discovery.discover_all_band_pairs("ignored")

    assert _tile_from_path(bef.b3) == _tile_from_path(aft.b3)
    assert _tile_from_path(bef.b8) == _tile_from_path(aft.b8)
    assert "20230603T084559" in bef.b3
    assert "20230618T084601" in aft.b3