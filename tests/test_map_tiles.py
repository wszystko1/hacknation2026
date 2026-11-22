"""Map tiles: addresses, the frozen zoom path, the grey stand-in, the disk cache and the freeze script."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.picker import frozen, tiles
from app.picker.webmercator import HALF_WORLD_M, lonlat_to_tile, tile_bbox_3857
from app.picker.zoompath import FIRST_ZOOM, LAST_ZOOM, layer_for_zoom, path_tiles

client = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def offline(monkeypatch) -> None:
    monkeypatch.setenv("GEODATA_OFFLINE", "1")


def url(layer: str, z: int, x: int, y: int) -> str:
    return f"/mapa/kafel/{layer}/{z}/{x}/{y}.jpg"


def test_tile_arithmetic_matches_the_web_mercator_grid() -> None:
    assert tile_bbox_3857(0, 0, 0) == (-HALF_WORLD_M, -HALF_WORLD_M, HALF_WORLD_M, HALF_WORLD_M)
    xmin, ymin, xmax, ymax = tile_bbox_3857(1, 1, 0)
    assert (xmin, ymin, xmax, ymax) == (0.0, 0.0, HALF_WORLD_M, HALF_WORLD_M)
    assert lonlat_to_tile(18.135, 53.27, 10) == (563, 332)
    x, y = lonlat_to_tile(18.135, 53.27, 17)
    west, south, east, north = tile_bbox_3857(17, x, y)
    assert west < 2018700 < east and south < 7033097 < north  # EPSG:3857 of the point, metres


def test_the_zoom_path_uses_the_base_map_then_the_orthophoto() -> None:
    path = path_tiles()
    assert {z for _, z, _, _ in path} == set(range(FIRST_ZOOM, LAST_ZOOM + 1))
    assert layer_for_zoom(8) == "podklad" and layer_for_zoom(9) == "orto"
    assert all(layer == layer_for_zoom(z) for layer, z, _, _ in path)


def test_every_tile_of_the_zoom_path_is_served_offline(offline, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GEODATA_CACHE_DIR", str(tmp_path))
    for layer, z, x, y in path_tiles():
        assert tiles.frozen_path(layer, z, x, y).is_file(), (layer, z, x, y)
        r = client.get(url(layer, z, x, y))
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/jpeg"
        assert r.content == tiles.frozen_path(layer, z, x, y).read_bytes()


def test_a_tile_outside_the_copy_offline_is_a_grey_tile_not_a_404(offline, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GEODATA_CACHE_DIR", str(tmp_path))
    x, y = lonlat_to_tile(15.0, 50.0, 17)  # inside the frame of Poland, far from the frozen path
    assert not tiles.frozen_path("orto", 17, x, y).is_file()
    r = client.get(url("orto", 17, x, y))
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert r.content == tiles.placeholder() and r.content.startswith(b"\xff\xd8")
    assert r.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "path",
    [url("mapa", 5, 17, 10), url("podklad", 20, 0, 0), url("podklad", 5, 32, 0), url("orto", 5, 0, 99)],
    ids=["unknown-layer", "zoom-20", "x-out-of-range", "y-out-of-range"],
)
def test_addresses_outside_the_grid_are_404(path: str) -> None:
    assert client.get(path).status_code == 404


def test_a_tile_comes_from_the_wms_with_a_3857_bbox_and_is_cached_on_disk(net, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GEODATA_CACHE_DIR", str(tmp_path / "cache"))
    r1 = client.get(url("orto", 16, 36000, 21000))
    r2 = client.get(url("orto", 16, 36000, 21000))
    assert r1.status_code == r2.status_code == 200
    assert r1.content == r2.content and r1.content.startswith(b"\xff\xd8")
    assert net.count("ORTO") == 1
    call = next(c for c in net.calls if "ORTO" in c)
    assert "SRS=EPSG%3A3857" in call and "WIDTH=256" in call and "HEIGHT=256" in call
    assert "BBOX=" in call
    assert (tmp_path / "cache" / "map_tiles" / "orto" / "16" / "36000" / "21000.jpg").is_file()
    assert r1.headers["cache-control"].startswith("public")


def test_the_base_map_layer_asks_the_topographic_service(net, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GEODATA_CACHE_DIR", str(tmp_path / "cache"))
    client.get(url("podklad", 9, 280, 163))
    assert net.count("img/guest/TOPO") >= 1  # the fake service answers 503, so the call is retried


def test_a_failing_wms_gives_the_grey_tile_and_is_not_cached(net, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GEODATA_CACHE_DIR", str(tmp_path / "cache"))
    net.down = True
    r = client.get(url("orto", 16, 36000, 21000))
    assert r.status_code == 200 and r.content == tiles.placeholder()
    assert not (tmp_path / "cache" / "map_tiles").exists()


def load_script():
    spec = importlib.util.spec_from_file_location("freeze_map", ROOT / "scripts" / "freeze_map.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_frozen_copy_is_at_most_10_mb() -> None:
    size = sum(p.stat().st_size for p in frozen.MAP_DIR.rglob("*") if p.is_file())
    assert size <= 10 * 1024 * 1024, size


def test_freeze_check_passes_on_the_committed_copy(capsys) -> None:
    assert load_script().check() == 0
    assert "brakuje: 0" in capsys.readouterr().out


def test_freeze_check_lists_missing_tiles_and_fails(tmp_path, monkeypatch, capsys) -> None:
    script = load_script()
    monkeypatch.setattr(tiles, "FROZEN_TILES", tmp_path / "tiles")
    monkeypatch.setattr(script.tiles, "frozen_path", lambda *a: tmp_path / "tiles" / "x" / "y.jpg")
    assert script.check() == 1
    out = capsys.readouterr().out
    layer, z, x, y = path_tiles()[0]
    assert f"brak kafla {layer}/{z}/{x}/{y}" in out
