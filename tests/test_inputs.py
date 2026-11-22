"""The three fields: date as dd.mm.rrrr, parcel as identifier, precinct + number or coordinates."""

from __future__ import annotations

import re
from datetime import date
from urllib.parse import urlencode

import httpx
import pytest
from fastapi.testclient import TestClient

from app.geodata import http
from app.inputs import (
    display_date,
    parse_coordinates,
    parse_date,
    parse_request,
    resolve_parcel,
)
from app.main import app

client = TestClient(app)
DOBRCZ = {"dzialka": "040303_2.0002.189/13", "data": "20.07.2023", "uprawa": "zboza_jare"}
GSM_ID = "100403_2.0011.144"  # the parcel in tests/fixtures/uldk_ok.txt (precinct Konstancin, number 144)
TODAY = date(2026, 11, 21)


def visible_text(page: str) -> str:
    page = re.sub(r"<(script|style|title|meta)\b.*?(</\1>|>)", " ", page, flags=re.S)
    return re.sub(r"<[^>]+>", " ", page)


# ---------------------------------------------------------------- date


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("20.07.2023", date(2023, 7, 20)),
        ("2023-07-20", date(2023, 7, 20)),
        ("1.2.2020", date(2020, 2, 1)),
        (" 20.07.2023 ", date(2023, 7, 20)),
    ],
)
def test_date_is_read_in_both_forms(text: str, expected: date) -> None:
    assert parse_date(text) == expected


@pytest.mark.parametrize("text", ["", "07/20/2023", "31.02.2023", "20-07-2023", "jutro"])
def test_other_date_forms_are_rejected(text: str) -> None:
    with pytest.raises(ValueError):
        parse_date(text)


def test_date_is_shown_as_dd_mm_rrrr() -> None:
    assert display_date("2023-07-20") == "20.07.2023"
    assert display_date("20.07.2023") == "20.07.2023"
    assert display_date("jutro") == "jutro"


def test_report_page_shows_the_date_as_dd_mm_rrrr_and_never_the_browser_formats() -> None:
    for typed in ("20.07.2023", "2023-07-20"):
        r = client.get("/raport?" + urlencode(DOBRCZ | {"data": typed, "widok": "doradca"}))
        assert r.status_code == 200
        text = visible_text(r.text)
        assert "20.07.2023" in text
        assert "07/20/2023" not in text and "2023-07-20" not in text
        assert re.search(r'<input id="f-data" name="data" type="text"[^>]*value="20.07.2023"', r.text)
        assert 'type="date"' not in r.text


def test_the_two_date_forms_give_the_same_report() -> None:
    a = client.get("/api/raport?" + urlencode(DOBRCZ)).json()
    b = client.get("/api/raport?" + urlencode(DOBRCZ | {"data": "2023-07-20"})).json()
    assert a["verdict"] == b["verdict"]


def test_a_bad_date_is_explained_in_polish_next_to_the_field() -> None:
    r = client.get("/raport?" + urlencode(DOBRCZ | {"data": "07/20/2023"}))
    assert r.status_code == 422
    assert re.search(r'class="field-error" id="e-data">Wpisz datę oceny w postaci dd.mm.rrrr', r.text)
    assert 'value="07/20/2023"' in r.text  # what was typed stays in the field


# ---------------------------------------------------------------- the button


def test_the_form_is_sent_by_htmx_and_the_button_is_disabled_while_it_runs() -> None:
    page = client.get("/").text
    form = re.search(r"<form class=\"pick\"[^>]*>", page, flags=re.S).group(0)
    assert 'hx-get="/raport"' in form
    assert 'hx-disabled-elt="find button"' in form
    assert 'action="/raport"' in form  # still a plain GET form without scripts
    assert "Oceń działkę" in page


# ---------------------------------------------------------------- three forms of the parcel


def test_identifier_needs_no_network() -> None:
    assert resolve_parcel("040303_2.0002.189/13") == "040303_2.0002.189/13"


@pytest.mark.parametrize(
    "text",
    [GSM_ID, "Konstancin 144", "Konstancin, 144", "52,0995 19,3502", "52.0995, 19.3502", "19.3502 52.0995"],
)
def test_identifier_precinct_with_number_and_coordinates_lead_to_the_same_parcel(net, text: str) -> None:
    assert resolve_parcel(text) == GSM_ID


def test_the_report_opens_from_each_form(net) -> None:
    for text in ("Konstancin 144", "52,0995 19,3502"):
        parcel_id, errors = parse_request(
            {"dzialka": text, "data": "21.11.2026", "uprawa": "rosliny_straczkowe"}, TODAY
        )
        assert not errors
        assert parcel_id.parcel_id == GSM_ID


def test_etrs_coordinates_in_the_national_grid_are_read() -> None:
    lon, lat = parse_coordinates("442332 600940")
    assert (round(lon, 2), round(lat, 2)) == (18.14, 53.27)


def test_demo_parcel_is_found_by_precinct_and_number_without_network(monkeypatch) -> None:
    monkeypatch.setenv("GEODATA_OFFLINE", "1")
    assert resolve_parcel("Dobrcz 189/13") == "040303_2.0002.189/13"
    assert resolve_parcel("53,2705 18,1353") == "040303_2.0002.189/13"


def test_several_matches_give_a_list_to_choose_from() -> None:
    answer = (
        "0\n040303_2.0002.5|kujawsko-pomorskie|powiat bydgoski|Dobrcz|Dobrcz|5\n"
        "040303_2.0004.5|kujawsko-pomorskie|powiat bydgoski|Dobrcz|Strzelce|5\n"
    )
    http.set_client(httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=answer))))
    r = client.get("/raport?" + urlencode(DOBRCZ | {"dzialka": "Dobrcz 5"}))
    assert r.status_code == 422
    assert re.search(r'id="e-dzialka">Obręb i numer pasują do 2 działek', r.text)
    for pid in ("040303_2.0002.5", "040303_2.0004.5"):
        assert f'href="/raport?dzialka={pid}&amp;data=20.07.2023&amp;uprawa=zboza_jare"' in r.text
    assert "obręb Strzelce" in r.text


def test_unknown_precinct_and_number_is_explained_next_to_the_field(net) -> None:
    r = client.get("/raport?" + urlencode(DOBRCZ | {"dzialka": "Konstancin 99999"}))
    assert r.status_code == 422
    assert re.search(r'id="e-dzialka">ULDK nie zna działki „Konstancin 99999”', r.text)


@pytest.mark.parametrize("text", ["abc", "12.5 13.5", "040303.0002.189"])
def test_text_that_is_none_of_the_three_forms_gets_the_format_hint(text: str) -> None:
    r = client.get("/raport?" + urlencode(DOBRCZ | {"dzialka": text}))
    assert r.status_code == 422
    assert re.search(r'name="dzialka"[^>]*aria-invalid="true"', r.text)
    assert 'class="field-error" id="e-dzialka">' in r.text
