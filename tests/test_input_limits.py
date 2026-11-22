"""Input length limits and the date check of the photo route: refused fast, valid input unchanged."""

import time
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.inputs import MAX_FIELD_LENGTH, parse_request, split_name
from app.main import app

client = TestClient(app)


def _timed(url: str, params: dict[str, str]):
    start = time.perf_counter()
    r = client.get(url, params=params)
    return r, time.perf_counter() - start


@pytest.mark.parametrize("junk", [",".join([""] * 10_000), "a" * 20_000, "x" * (MAX_FIELD_LENGTH + 1)])
@pytest.mark.parametrize("url", ["/raport", "/api/raport"])
def test_long_parcel_is_refused_fast(url: str, junk: str) -> None:
    r, took = _timed(url, {"dzialka": junk, "data": "20.07.2023", "uprawa": "pszenica_ozima"})
    assert r.status_code == 422
    assert took < 0.2


def test_30000_commas_are_refused_fast() -> None:
    start = time.perf_counter()
    req, errors = parse_request({"dzialka": "a" + "," * 30_000, "data": "20.07.2023", "uprawa": "x"})
    assert req is None
    assert errors[0].field == "dzialka"
    assert time.perf_counter() - start < 0.2


def test_long_parcel_message_is_polish() -> None:
    req, errors = parse_request({"dzialka": "a" * 81, "data": "20.07.2023", "uprawa": "x"})
    assert req is None
    assert "80 znaków" in errors[0].message


def test_split_name_is_linear_on_commas() -> None:
    start = time.perf_counter()
    assert split_name("a" + "," * 30_000) is None
    assert time.perf_counter() - start < 0.2


@pytest.mark.parametrize("day", ["0001-01-01", "2015-12-31", "2999-01-01", "nie-data", "01.01.0001"])
def test_photo_refuses_bad_date(day: str) -> None:
    r, took = _timed("/raport/zdjecie", {"dzialka": "040303_2.0002.189/13", "data": day})
    assert r.status_code == 422
    assert took < 0.2


def test_photo_refuses_long_parcel() -> None:
    r, _ = _timed("/raport/zdjecie", {"dzialka": "9" * 81, "data": "2023-07-20"})
    assert r.status_code == 422


def test_photo_valid_date_passes_the_check() -> None:
    r, _ = _timed("/raport/zdjecie", {"dzialka": "bzdura", "data": date.today().isoformat()})
    assert r.status_code == 404


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Dobrcz 189/13", ("Dobrcz", "189/13")),
        ("Dobrcz, 189/13", ("Dobrcz", "189/13")),
        ("Nowa Wieś 12", ("Nowa Wieś", "12")),
        ("189/13", None),
        ("Dobrcz189", None),
        ("Dobrcz 12 ab!", None),
    ],
)
def test_split_name_formats(text: str, expected: tuple[str, str] | None) -> None:
    assert split_name(text) == expected
