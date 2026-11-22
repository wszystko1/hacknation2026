"""The second variant of the verdict: Doroszewski-Górski evaporation in the advisor view."""

from __future__ import annotations

import re
from datetime import date

from fastapi.testclient import TestClient

from app.drought.variants import inputs_file
from app.main import app
from app.models import Report

client = TestClient(app)
PARAMS = "dzialka=040303_2.0002.189/13&data=2023-07-20&uprawa=zboza_jare"


def _report() -> Report:
    r = client.get(f"/api/raport?{PARAMS}")
    assert r.status_code == 200
    return Report.model_validate(r.json())


def test_demo_copy_has_frozen_temperature_and_sunshine() -> None:
    assert inputs_file("040303_2.0002.189/13", "2023-07-20").is_file()


def test_both_variants_are_tagged_and_the_verdict_stays_on_fao56() -> None:
    r = _report()
    assert r.verdict.et_method == "fao56"
    assert r.verdict_dg is not None and r.verdict_dg.et_method == "dg"
    assert r.verdict_dg.period is not None and r.verdict_dg.period.end <= date(2023, 7, 20)
    assert r.verdict_dg.state in {"below", "above"}


def test_advisor_view_names_the_source_and_the_farmer_view_does_not_have_it() -> None:
    advisor = client.get(f"/raport?{PARAMS}&widok=doradca").text
    assert "Doroszewski" in advisor and "2012" in advisor and "plakietka-dg" in advisor
    farmer = client.get(f"/raport?{PARAMS}&widok=rolnik").text
    outside = re.sub(r'<details class="b-row" id="wiersz-dla-doradcy".*?</details>', " ", farmer, flags=re.S)
    assert "plakietka-dg" not in outside and "plakietka-dg" in farmer  # only in the collapsed row


def test_print_view_has_the_second_variant() -> None:
    assert "plakietka-dg" in client.get(f"/raport/druk?{PARAMS}").text
