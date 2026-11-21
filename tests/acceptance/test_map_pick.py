"""K4: the parcel can be pointed at on the map instead of typed.

A click on the start map (or on a neighbouring field on the report map) becomes a lon/lat point; the server turns
it into a cadastral parcel (ULDK GetParcelByXY) and returns the identifier that goes into the "dzialka" field,
with the area for the confirmation card. The demo area works from the frozen sample, without network: the tests
point an empty cache directory at GEODATA_CACHE_DIR and set GEODATA_OFFLINE=1.
"""

from __future__ import annotations

import re

import pytest

from tests.acceptance.helpers import DOBRCZ, GSM_TODAY, client

# Points inside the demo parcels, far from their edges (189/13: about 187 m, 144: about 35 m).
INSIDE_DOBRCZ = {"lon": "18.1353", "lat": "53.2705"}
INSIDE_GSM = {"lon": "19.3502", "lat": "52.0995"}
# About 160 m west of parcel 189/13: the field a farmer clicks on the report map to move to the neighbour.
NEIGHBOUR_OF_DOBRCZ = {"lon": "18.1300", "lat": "53.2705"}

PARCEL_ID = re.compile(r"^\d{6}_\d\.\d{4}\.\S+$")


@pytest.fixture
def offline_sample(monkeypatch, tmp_path) -> None:
    """Only the frozen sample in the repository can answer: no network, no local download cache."""
    monkeypatch.setenv("GEODATA_OFFLINE", "1")
    monkeypatch.setenv("GEODATA_CACHE_DIR", str(tmp_path))


def pick(point: dict) -> object:
    from urllib.parse import urlencode

    return client.get(f"/api/dzialka?{urlencode(point)}")


@pytest.mark.xfail(reason="not built yet", strict=False)
@pytest.mark.usefixtures("offline_sample")
@pytest.mark.parametrize(
    ("point", "expected_id", "area_ha"),
    [(INSIDE_DOBRCZ, DOBRCZ["dzialka"], 21.53), (INSIDE_GSM, GSM_TODAY["dzialka"], 2.48)],
)
def test_click_on_a_known_point_gives_the_parcel_from_the_sample(
    point: dict, expected_id: str, area_ha: float
) -> None:
    r = pick(point)
    assert r.status_code == 200, r.text[:500]
    body = r.json()
    assert body["dzialka"] == expected_id
    assert body["pow_ha"] == pytest.approx(area_ha, abs=0.01)


@pytest.mark.xfail(reason="not built yet", strict=False)
@pytest.mark.usefixtures("offline_sample")
def test_the_picked_identifier_opens_the_same_report() -> None:
    picked = pick(INSIDE_DOBRCZ).json()["dzialka"]
    r = client.get(f"/api/raport?dzialka={picked}&data={DOBRCZ['data']}&uprawa={DOBRCZ['uprawa']}")
    assert r.status_code == 200, r.text[:500]
    assert r.json()["parcel"]["id"] == DOBRCZ["dzialka"]


@pytest.mark.xfail(reason="not built yet", strict=False)
@pytest.mark.usefixtures("offline_sample")
def test_click_on_the_neighbouring_field_gives_another_parcel() -> None:
    r = pick(NEIGHBOUR_OF_DOBRCZ)
    assert r.status_code == 200, r.text[:500]
    neighbour = r.json()["dzialka"]
    assert neighbour != DOBRCZ["dzialka"]
    assert PARCEL_ID.match(neighbour), neighbour


@pytest.mark.xfail(reason="not built yet", strict=False)
@pytest.mark.parametrize(
    "point",
    [{"lon": "13.4050", "lat": "52.5200"}, {"lon": "abc", "lat": "53.2705"}, {"lon": "18.1353"}],
    ids=["outside-poland", "not-a-number", "missing-lat"],
)
def test_a_point_without_a_parcel_is_an_explicit_error(point: dict) -> None:
    r = pick(point)
    assert r.status_code == 422
    errors = r.json()["bledy"]
    assert errors[0]["field"] == "dzialka"
    assert errors[0]["message"]


@pytest.mark.xfail(reason="not built yet", strict=False)
@pytest.mark.usefixtures("offline_sample")
def test_a_point_outside_the_sample_offline_is_an_explicit_error() -> None:
    r = pick({"lon": "22.5000", "lat": "49.2000"})
    assert r.status_code == 422
    assert r.json()["bledy"][0]["field"] == "dzialka"
