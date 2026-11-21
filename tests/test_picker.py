"""Parcel under a map point: input checks, the frozen outlines, the live lookup and its failures."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.geodata.errors import ParcelNotFound, UpstreamError
from app.geodata.models import Parcel
from app.main import app
from app.picker import frozen, routes

client = TestClient(app)
DOBRCZ = "040303_2.0002.189/13"


@pytest.fixture
def offline(monkeypatch) -> None:
    monkeypatch.setenv("GEODATA_OFFLINE", "1")


def interior_point(parcel: frozen.FrozenParcel) -> tuple[float, float]:
    """A point inside the outline (EPSG:2180): the middle of the widest run of inside points on a scan line."""
    xmin, ymin, xmax, ymax = parcel.bbox_2180
    best, best_width = (0.0, 0.0), -1.0
    for k in range(1, 40):
        y = ymin + (ymax - ymin) * k / 40
        run: list[float] = []
        for i in range(401):
            x = xmin + (xmax - xmin) * i / 400
            if parcel.contains(x, y):
                run.append(x)
                continue
            if run and run[-1] - run[0] > best_width:
                best_width, best = run[-1] - run[0], ((run[0] + run[-1]) / 2, y)
            run = []
        if run and run[-1] - run[0] > best_width:
            best_width, best = run[-1] - run[0], ((run[0] + run[-1]) / 2, y)
    assert best_width >= 0, parcel.dzialka
    return best


def lonlat(x: float, y: float) -> dict:
    from pyproj import Transformer

    lon, lat = Transformer.from_crs(2180, 4326, always_xy=True).transform(x, y)
    return {"lon": f"{lon:.7f}", "lat": f"{lat:.7f}"}


@pytest.mark.parametrize(
    "query",
    ["", "lon=18.1", "lat=53.2", "lon=abc&lat=53.2", "lon=18.1&lat=", "lon=nan&lat=53.2", "lon=18.1&lat=inf"],
)
def test_missing_or_non_numeric_coordinates_are_refused_in_polish(query: str) -> None:
    r = client.get(f"/api/dzialka?{query}")
    assert r.status_code == 422
    error = r.json()["bledy"][0]
    assert error["field"] == "dzialka"
    assert "liczb" in error["message"]


def test_a_point_outside_poland_is_refused_without_asking_ulduk(monkeypatch) -> None:
    def boom(*args, **kwargs):
        raise AssertionError("ULDK must not be asked")

    monkeypatch.setattr(routes, "fetch_parcel_by_lonlat", boom)
    r = client.get("/api/dzialka?lon=13.4050&lat=52.5200")
    assert r.status_code == 422
    assert "poza Polską" in r.json()["bledy"][0]["message"]


def test_comma_decimals_are_accepted(offline) -> None:
    r = client.get("/api/dzialka?lon=18,1353&lat=53,2705")
    assert r.status_code == 200
    assert r.json()["dzialka"] == DOBRCZ


def test_the_answer_has_the_fields_of_the_contract(offline) -> None:
    body = client.get("/api/dzialka?lon=18.1353&lat=53.2705").json()
    assert set(body) == {"dzialka", "numer", "obreb", "gmina", "pow_ha", "obrys_4326"}
    assert (body["numer"], body["obreb"], body["gmina"]) == ("189/13", "Dobrcz", "Dobrcz")
    ring = body["obrys_4326"][0]
    assert ring[0] == ring[-1] and 18.0 < ring[0][0] < 18.3 and 53.2 < ring[0][1] < 53.3


def test_the_demo_parcels_are_in_the_frozen_copy() -> None:
    ids = {p.dzialka for p in frozen.load_all()}
    assert {DOBRCZ, "100403_2.0011.144"} <= ids


@pytest.mark.xfail(
    reason="ULDK refused the machine that froze the copy (redirect to a stub); run scripts/freeze_map.py --parcels",
    strict=False,
)
def test_neighbours_of_the_main_demo_parcel_are_frozen() -> None:
    assert (
        len([p for p in frozen.load_all() if p.dzialka != DOBRCZ and p.dzialka.startswith("040303_2.0002.")])
        >= 6
    )


def test_a_point_inside_any_frozen_outline_gives_that_parcel(offline) -> None:
    for parcel in frozen.load_all():
        x, y = interior_point(parcel)
        r = client.get("/api/dzialka", params=lonlat(x, y))
        assert r.status_code == 200, parcel.dzialka
        assert r.json()["dzialka"] == parcel.dzialka


def test_a_point_inside_a_hole_is_not_in_the_parcel() -> None:
    outer = [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0], [0.0, 0.0]]
    hole = [[4.0, 4.0], [6.0, 4.0], [6.0, 6.0], [4.0, 6.0], [4.0, 4.0]]
    p = frozen.FrozenParcel("x", "1", "o", "g", 0.0, [outer, hole], [], (0.0, 0.0, 10.0, 10.0))
    assert p.contains(2.0, 2.0)
    assert not p.contains(5.0, 5.0)
    assert not p.contains(11.0, 5.0)


def _live_parcel() -> Parcel:
    ring_2180 = [
        [500000.0, 500000.0],
        [500100.0, 500000.0],
        [500100.0, 500100.0],
        [500000.0, 500100.0],
        [500000.0, 500000.0],
    ]
    ring_4326 = [[19.0, 52.0], [19.001, 52.0], [19.001, 52.001], [19.0, 52.001], [19.0, 52.0]]
    return Parcel(
        id="141201_1.0001.5/2", voivodeship="mazowieckie", county="powiat x", commune="Gmina X",
        precinct="Obręb X", number="5/2", area_ha=1.0049, rings_2180=[ring_2180], rings_4326=[ring_4326],
        centroid_2180=[500050.0, 500050.0], centroid_4326=[19.0005, 52.0005],
        bbox_2180=[500000.0, 500000.0, 500100.0, 500100.0], bbox_4326=[19.0, 52.0, 19.001, 52.001],
    )  # fmt: skip


def test_a_point_outside_the_copy_is_looked_up_live(monkeypatch) -> None:
    from app.geodata.models import SourceResult

    monkeypatch.setattr(
        routes,
        "fetch_parcel_by_lonlat",
        lambda lon, lat, deadline=None: SourceResult("parcel", "ok", _live_parcel()),
    )
    r = client.get("/api/dzialka?lon=21.0&lat=52.2")
    assert r.status_code == 200
    body = r.json()
    assert body["dzialka"] == "141201_1.0001.5/2"
    assert (body["numer"], body["obreb"], body["gmina"], body["pow_ha"]) == ("5/2", "Obręb X", "Gmina X", 1.0)
    assert body["obrys_4326"][0][0] == [19.0, 52.0]


@pytest.mark.parametrize(
    ("error", "fragment"),
    [(ParcelNotFound("ULDK: 1"), "nie ma działki"), (UpstreamError("HTTP 503"), "Nie mamy odpowiedzi")],
    ids=["no-parcel", "no-answer"],
)
def test_live_failures_are_explicit_422(monkeypatch, error: Exception, fragment: str) -> None:
    def fail(lon, lat, deadline=None):
        raise error

    monkeypatch.setattr(routes, "fetch_parcel_by_lonlat", fail)
    r = client.get("/api/dzialka?lon=21.0&lat=52.2")
    assert r.status_code == 422
    assert r.json()["bledy"][0]["field"] == "dzialka"
    assert fragment in r.json()["bledy"][0]["message"]


def test_offline_point_outside_the_copy_says_what_is_known(offline) -> None:
    r = client.get("/api/dzialka?lon=22.5&lat=49.2")
    assert r.status_code == 422
    assert "Bez sieci" in r.json()["bledy"][0]["message"]
