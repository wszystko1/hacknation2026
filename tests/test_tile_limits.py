"""Map tile requests outside Poland or zoom 9-19 are refused; the tile cache stays under its size cap."""

import os

from fastapi.testclient import TestClient

from app.geodata import cache
from app.main import app
from app.picker import tiles


def test_zoom_and_frame_limits():
    x0, x1, y0, y1 = tiles.poland_range(12)
    assert tiles.valid_address("podklad", 12, x0, y0)
    assert tiles.valid_address("orto", 12, x1, y1)
    assert not tiles.valid_address("podklad", 12, x0 - 1, y0)
    assert not tiles.valid_address("podklad", 12, x0, y1 + 1)
    assert not tiles.valid_address("podklad", 8, 2, 2)
    assert not tiles.valid_address("podklad", 20, 0, 0)


def test_route_refuses_outside_frame():
    client = TestClient(app)
    x0, _, y0, _ = tiles.poland_range(10)
    assert client.get(f"/mapa/kafel/podklad/10/{x0 - 5}/{y0}.jpg").status_code == 404
    assert client.get("/mapa/kafel/podklad/5/1/1.jpg").status_code == 404


def test_prune_removes_oldest_first(tmp_path):
    for i in range(10):
        f = tmp_path / f"{i}.jpg"
        f.write_bytes(b"x" * 100)
        os.utime(f, (1000 + i, 1000 + i))
    assert cache.prune(tmp_path, 10_000) == 0
    removed = cache.prune(tmp_path, 500)
    assert removed >= 5
    left = sorted(p.name for p in tmp_path.iterdir())
    assert "9.jpg" in left and "0.jpg" not in left
    assert sum(p.stat().st_size for p in tmp_path.iterdir()) <= 450
