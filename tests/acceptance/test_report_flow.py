"""K5: a report for any parcel and date of the last 10 years, today included (out of the monitoring period),
in at most 30 s; print view; an explicit error for a wrong number; works offline from the cache; README."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from app.models import OUT_OF_SEASON
from tests.acceptance.helpers import DOBRCZ, GSM_TODAY, client, html, query, report


def test_demo_parcel_report_in_under_30_s() -> None:
    started = time.monotonic()
    r = report()
    assert time.monotonic() - started < 30
    assert r.parcel.area_ha == pytest.approx(21.53, abs=0.01)
    assert r.verdict.kbw_mm is not None
    assert len(r.sections) == 8


def test_print_view_is_the_same_report() -> None:
    page = html(DOBRCZ, path="/raport/druk")
    r = report()
    assert "Działka 189/13" in page
    assert r.verdict.sentence in page.replace("&#34;", '"')


def test_wrong_number_is_an_explicit_error() -> None:
    r = client.get("/api/raport?dzialka=040303_2.0002&data=2023-07-20&uprawa=zboza_jare")
    assert r.status_code == 422
    assert r.json()["bledy"][0]["field"] == "dzialka"


def test_unknown_parcel_offline_is_an_explicit_error(monkeypatch) -> None:
    monkeypatch.setenv("GEODATA_OFFLINE", "1")
    r = client.get(f"/raport?{query(DOBRCZ, dzialka='040303_2.0002.99999')}")
    assert r.status_code == 422
    assert 'class="field-error" id="e-dzialka"' in r.text


def test_works_offline_from_the_frozen_copy(monkeypatch) -> None:
    monkeypatch.setenv("GEODATA_OFFLINE", "1")
    r = report()
    assert r.data_copy is not None


def test_a_date_from_2016_works() -> None:
    r = report(DOBRCZ, data="2016-08-10")
    assert r.verdict.period is not None
    assert r.verdict.period.start.year == 2016


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_today_is_out_of_the_monitoring_period_with_last_season_and_plan() -> None:
    r = report(GSM_TODAY)
    assert r.verdict.state == "out_of_season"
    assert r.verdict.season_year == 2026
    assert OUT_OF_SEASON in html(GSM_TODAY)
    assert r.section("plan").actions or r.actions


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_readme_explains_windows_run_without_make_sources_licences_limits() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    for text in ("uv run python -m app", "Windows", "Licencj", "Uczciwe ograniczenia", "Dz.U. 2019 poz. 739"):
        assert text in readme, text
