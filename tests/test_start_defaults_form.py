"""The start form is pre-filled with the demo parcel; a link or a user's own input is never overwritten."""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from app.main import DEFAULT_FORM, app

client = TestClient(app)


def test_start_has_three_defaults_and_a_note() -> None:
    page = client.get("/").text
    assert 'value="040303_2.0002.189/13"' in page
    assert 'value="20.07.2023"' in page
    assert re.search(r'<option value="zboza_jare"\s+selected', page)
    assert "każde pole możesz zmienić" in page


def test_link_values_are_kept() -> None:
    page = client.get("/?dzialka=100403_2.0011.144&data=2026-11-21&uprawa=rosliny_straczkowe").text
    assert 'value="100403_2.0011.144"' in page
    assert 'value="21.11.2026"' in page
    assert re.search(r'<option value="rosliny_straczkowe"\s+selected', page)
    assert not re.search(r'<option value="zboza_jare"\s+selected', page)


def test_empty_parameter_does_not_return_to_default() -> None:
    page = client.get("/?dzialka=&data=2026-11-21&uprawa=").text
    assert 'id="f-dzialka" name="dzialka" value=""' in page


def test_report_route_with_defaults_gives_a_verdict() -> None:
    r = client.get("/raport", params=DEFAULT_FORM)
    assert r.status_code == 200
    assert "189/13" in r.text and "report-head" in r.text


def test_wrong_number_is_not_replaced_by_default() -> None:
    r = client.get("/raport", params={**DEFAULT_FORM, "dzialka": "zly numer"})
    assert r.status_code == 422
    assert 'value="zly numer"' in r.text
    assert 'value="040303_2.0002.189/13"' not in r.text
