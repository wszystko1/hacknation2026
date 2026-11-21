"""The report names what is missing in one sentence and shows one total of the time spent on sources."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import SECTION_ORDER, Report
from app.report import total_time_s
from app.sections import empty_sentence, placeholder

client = TestClient(app)

PARCELS = [
    "dzialka=040303_2.0002.189/13&data=2023-07-20&uprawa=zboza_jare",
    "dzialka=100403_2.0011.144&data=2026-11-21&uprawa=rosliny_straczkowe",
]
ROUTES = ["/raport?{p}", "/raport?{p}&widok=doradca", "/raport/druk?{p}"]


def _empty_paragraphs(html: str) -> list[str]:
    """Texts of every paragraph that the section template draws for a section without a result."""
    found = re.findall(r'<p class="(?:empty|placeholder)[^"]*"[^>]*>(.*?)</p>', html, re.S)
    return [re.sub(r"<[^>]+>", "", t).strip() for t in found]


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("parcel", PARCELS)
def test_no_section_promises_a_result(route: str, parcel: str) -> None:
    r = client.get(route.format(p=parcel))
    assert r.status_code == 200
    assert 'class="placeholder' not in r.text
    for text in _empty_paragraphs(r.text):
        assert text.startswith("Brak:") and "Tu pojawi" not in text, text


@pytest.mark.parametrize("parcel", PARCELS)
def test_sections_built_by_placeholder_start_with_brak(parcel: str) -> None:
    report = Report.model_validate(client.get(f"/api/raport?{parcel}").json())
    for section in report.sections:
        if section.state == "missing":
            assert section.reason.startswith("Brak:"), (section.id, section.reason)
            assert "Tu pojawi" not in section.reason


def test_placeholder_turns_a_promise_into_a_gap() -> None:
    section = placeholder("historia", "Historia", "Tu pojawi się wykres 10 sezonów bo brak pogody z IMGW.")
    assert section.state == "missing"
    assert section.reason == "Brak: wykres 10 sezonów bo brak pogody z IMGW."
    assert [p.text for p in section.summary] == [section.reason]


def test_placeholder_keeps_a_sentence_that_already_names_the_gap() -> None:
    what = "Brak: oceny SMSR dla gminy bo wykaz IUNG nie odpowiedział."
    assert empty_sentence(what) == what
    assert placeholder("gmina", "Gmina", what).reason == what


def test_placeholder_that_waits_is_loading_and_says_for_what() -> None:
    section = placeholder("historia", "Historia", "wykresu 10 sezonów", waiting_for="pogoda z 10 lat (IMGW)")
    assert section.state == "loading"
    assert section.waiting_for == "pogoda z 10 lat (IMGW)"


def test_every_section_id_can_be_a_placeholder() -> None:
    for sid, n, _ in SECTION_ORDER:
        assert placeholder(sid, "x", "Brak: czegoś bo nie ma.").n == n


def test_total_is_the_sum_of_the_source_rows() -> None:
    report = Report.model_validate(client.get(f"/api/raport?{PARCELS[0]}").json())
    assert report.sources
    assert abs(report.total_s - sum(r.elapsed_s or 0 for r in report.sources)) <= 0.1
    assert report.total_s == total_time_s(report.sources)


def test_one_total_on_the_map_card_and_in_the_sources_section() -> None:
    html = client.get(f"/raport?{PARCELS[0]}").text
    card = re.findall(r"razem\s+([\d,]+) s", html)
    report = Report.model_validate(client.get(f"/api/raport?{PARCELS[0]}").json())
    chip = next(s.chip for s in report.sections if s.id == "zrodla")
    assert chip.startswith("razem ") and chip.endswith(" s")
    assert card, "the map card shows no total"
    assert {c for c in card} == {chip.removeprefix("razem ").removesuffix(" s")}
    assert len(set(re.findall(r"razem\s+[\d,]+ s", html))) == 1


def test_the_adviser_view_states_each_gap_with_its_reason() -> None:
    html = client.get(f"/raport?{PARCELS[0]}&widok=doradca").text
    assert _empty_paragraphs(html), "no section states its gap"
