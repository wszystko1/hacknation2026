"""Quality rules of the Sentinel-2 reading: shrunken outline, clear share, NDVI spread, the 1000 offset."""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest
from rasterio.transform import from_origin

from app.geodata import SceneIndex, fetch_satellite, satellite
from app.geodata.satellite import INNER_BUFFER_M, MIN_CLEAR_SHARE, _edge_distance, simplify_item
from tests.test_geodata_satellite import make_scene, parcel  # noqa: F401 - parcel is a fixture


def _feature(baseline: str, day: str, **props: object) -> dict:
    assets = {k: {"href": f"https://example.invalid/{k}.tif"} for k in ("B04", "B08", "B8A", "B11", "SCL")}
    return {
        "id": "S2_x",
        "properties": {"datetime": f"{day}T10:00:00Z", "s2:processing_baseline": baseline, **props},
        "assets": assets,
    }


def test_offset_is_removed_from_baseline_04_00_on_and_only_then() -> None:
    after = simplify_item(_feature("04.00", "2022-01-25"))
    before = simplify_item(_feature("03.01", "2022-01-20"))
    assert after is not None and before is not None
    assert after["dn_offset"] == -1000.0
    assert before["dn_offset"] == 0.0
    assert simplify_item(_feature("05.11", "2024-06-01"))["dn_offset"] == -1000.0


def test_offset_already_removed_by_the_catalogue_is_not_removed_twice() -> None:
    names = {
        k: {"href": f"https://example.invalid/{k}.tif"} for k in ("red", "nir", "nir08", "swir16", "scl")
    }
    feature = {
        "id": "S2_y",
        "properties": {
            "datetime": "2024-06-01T10:00:00Z",
            "s2:processing_baseline": "05.11",
            "earthsearch:boa_offset_applied": True,
        },
        "assets": names,
    }
    assert simplify_item(feature)["dn_offset"] == 0.0


def test_the_outline_is_shrunk_by_ten_metres() -> None:
    assert INNER_BUFFER_M == 10
    ring = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0), (0.0, 0.0)]
    distance = _edge_distance(ring, (10, 10), from_origin(0, 100, 10, 10))
    assert distance.min() == 5.0 and distance.max() == 45.0
    assert int((distance >= INNER_BUFFER_M).sum()) == 64  # 8 x 8 of 10 x 10 pixels stay


def test_ndvi_spread_is_p90_minus_p10_of_the_clear_pixels(net, tmp_path, parcel) -> None:  # noqa: F811
    scene = make_scene(
        tmp_path, parcel, "even", "2024-06-18", red=1500, nir=5000, nir08=5000, swir=3000, scl=4
    )
    net.stac_payload = {"features": [scene]}
    result = fetch_satellite(parcel, date(2024, 6, 18), history_years=0, today=date(2026, 11, 21))
    current = result.data.current
    assert current.ndvi_spread == pytest.approx(0.0, abs=1e-6)  # one flat raster: no spread
    assert current.pixels < 800 * 800 / 100  # fewer pixels than the whole outline: the edge is out


def test_scene_below_the_clear_share_is_dropped_with_the_reason(monkeypatch, parcel) -> None:  # noqa: F811
    assert 0 < MIN_CLEAR_SHARE < 1
    item = {
        "id": "S2_a",
        "date": "2024-06-18",
        "cloud": 3.0,
        "epsg": 32634,
        "dn_offset": -1000.0,
        "hrefs": {},
    }
    thin = SceneIndex("S2_a", "2024-06-18", 0, 3.0, 0.7, 0.3, MIN_CLEAR_SHARE / 2, 500, ndvi_spread=0.1)
    monkeypatch.setattr(satellite, "search_scenes", lambda *a, **k: [item])
    monkeypatch.setattr(satellite, "scene_index", lambda *a, **k: thin)
    result = fetch_satellite(parcel, date(2024, 6, 18), history_years=0, today=date(2026, 11, 21))
    assert result.data.current is None
    assert any(n.startswith("dropped:") and "cloud-free" in n for n in result.notes)
    np.testing.assert_allclose(thin.valid_fraction, MIN_CLEAR_SHARE / 2)
