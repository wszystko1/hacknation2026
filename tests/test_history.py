"""Sections 1 and 3: charts, short sentences, "Jak to policzono" and no promise of a result on either route."""

from __future__ import annotations

import re

import pytest

from app.models import Report
from tests.acceptance.helpers import DOBRCZ, GSM_TODAY, html, report

PARCELS = [DOBRCZ, GSM_TODAY]
ROUTES = ["/raport", "/raport/druk"]


def section_html(page: str, section_id: str) -> str:
    return re.search(rf'<section id="{section_id}".*?</section>', page, flags=re.S).group(0)


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("params", PARCELS)
@pytest.mark.parametrize("section_id", ["historia", "przyczyny"])
def test_section_has_a_chart_with_a_title_sentences_and_the_calculation(
    route: str, params: dict, section_id: str
) -> None:
    page = html(params, route)
    sec = section_html(page, section_id)
    assert "Tu pojawi" not in sec
    svg = re.search(r'<svg class="ch".*?</svg>', sec, flags=re.S)
    assert svg and re.search(r"<title>[^<]+</title>", svg.group(0))
    sentences = re.findall(r"<p>", re.sub(r"<details.*?</details>", "", sec, flags=re.S))
    assert 2 <= len(sentences) <= 3
    assert "<summary>Jak to policzono</summary>" in sec
    for size in re.findall(r'font-size="([\d.]+)"', svg.group(0)):
        assert float(size) >= 16


@pytest.mark.parametrize("params", PARCELS)
def test_ten_seasons_summary_and_marks(params: dict) -> None:
    r = report(params)
    s = r.section("historia")
    assert s.state == "ready" and s.chart_svg.startswith("<svg")
    assert re.search(r"\d+ z 10", "".join(p.text for p in s.summary))
    assert s.chart_svg.count('class="s-thr"') >= 1


def test_chart_marks_the_smsr_assessment_of_the_commune_since_2020() -> None:
    s = report(DOBRCZ).section("historia")
    assert ">SMSR<" in s.chart_svg and ">susza<" in s.chart_svg
    assert any("2023: +" in kv.value for kv in s.advisor)


@pytest.mark.parametrize("params", PARCELS)
def test_no_section_of_the_report_promises_a_result(params: dict) -> None:
    for route in ROUTES:
        assert "Tu pojawi" not in html(params, route)


def test_missing_weather_gives_one_sentence_with_the_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.sections import historia, przyczyny
    from tests.test_diagnosis import make_context

    ctx = make_context(DOBRCZ, drop_weather=True)
    for section in (historia.build(ctx), przyczyny.build(ctx)):
        assert section.state == "missing"
        assert section.reason.startswith("Brak:") and " bo " in section.reason
        assert not section.chart_svg


def test_models_validate_the_sections() -> None:
    r = report(DOBRCZ)
    assert Report.model_validate(r.model_dump()).section("przyczyny").state == "ready"
