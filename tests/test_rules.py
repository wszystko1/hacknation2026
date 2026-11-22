"""Soil, crop and irrigation rules: conditions, causes, terms, the irrigation decision and the pages that show them."""

from __future__ import annotations

import re
from datetime import date
from types import SimpleNamespace

import pytest

from app.advice import rules
from app.advice.catalog import load_catalog
from app.models import CropGroup
from tests.acceptance.helpers import DOBRCZ, GSM_TODAY, client, html, query, report

PARCELS = [DOBRCZ, GSM_TODAY]
IDS = ["dobrcz", "gsm-today"]


def _ctx(soil: str | None, crop: CropGroup = CropGroup.ZBOZA_JARE) -> SimpleNamespace:
    return SimpleNamespace(
        soil=SimpleNamespace(category=soil) if soil else None,
        request=SimpleNamespace(crop=crop),
    )


def test_subsoiling_only_on_medium_and_heavy_soils() -> None:
    row = load_catalog()["gleboszowanie"]
    assert not rules._applies(row, _ctx("I"))
    assert not rules._applies(row, _ctx("II"))
    assert rules._applies(row, _ctx("III"))
    assert rules._applies(row, _ctx("IV"))
    assert not rules._applies(row, _ctx(None))  # a soil condition cannot be checked without the soil


def test_subsoiling_of_tracks_only_on_light_soils() -> None:
    row = load_catalog()["gleboszowanie-sciezek"]
    assert rules._applies(row, _ctx("II"))
    assert not rules._applies(row, _ctx("III"))


def test_sowing_rules_do_not_apply_to_orchards_and_spring_ploughing_not_to_winter_crops() -> None:
    catalog = load_catalog()
    assert not rules._applies(catalog["termin-siewu"], _ctx("II", CropGroup.DRZEWA_OWOCOWE))
    assert not rules._applies(catalog["rezygnacja-z-orki-wiosennej"], _ctx("II", CropGroup.ZBOZA_OZIME))
    assert rules._applies(catalog["rezygnacja-z-orki-wiosennej"], _ctx("II", CropGroup.ZBOZA_JARE))


def test_root_zone_row_is_not_turned_into_an_action() -> None:
    assert not rules._applies(load_catalog()["nawadnianie-termin-fao56"], _ctx("II"))


@pytest.mark.parametrize("params", PARCELS, ids=IDS)
def test_soil_and_irrigation_actions_follow_the_same_ranking_rules(params: dict) -> None:
    r = report(params)
    causes = {c.words for c in r.diagnosis.causes}
    for group in ("uprawa", "nawadnianie"):
        actions = [a for a in r.actions if a.group == group]
        assert 1 <= len(actions) <= 3, group
        for a in actions:
            assert a.causes and set(a.causes) <= causes and a.cause == a.causes[0], a.id
        counts = [len(a.causes) for a in actions]
        assert counts == sorted(counts, reverse=True), (group, counts)


@pytest.mark.parametrize("params", PARCELS, ids=IDS)
def test_every_action_has_a_term_and_a_catalogue_source(params: dict) -> None:
    r = report(params)
    catalog = load_catalog()
    for group in ("uprawa", "nawadnianie"):
        actions = [a for a in r.actions if a.group == group]
        with_term = [a for a in actions if a.when and not a.when.startswith("Brak")]
        assert len(with_term) >= 2, group
        for a in actions:
            row = catalog[a.id]
            assert row.source_doc.split(",")[0].split(";")[0] in a.source, a.id
            assert re.search(r"\d", a.sentence), a.sentence
            if a.group == "uprawa":
                assert a.due is not None and re.search(r"\d{2}\.\d{2}\.\d{4}", a.when), a.when


def test_effect_is_printed_only_with_a_full_source() -> None:
    r = report()
    catalog = load_catalog()
    for a in r.actions:
        if a.effect:
            assert "literatura" in a.effect and catalog[a.id].has_full_source(), a.id
    assert any(a.id == "mulczowanie" and a.effect for a in r.actions)


def test_irrigation_says_yes_in_the_drought_period_with_dose_in_mm_and_m3() -> None:
    r = report(DOBRCZ)
    first = next(a for a in r.actions if a.group == "nawadnianie")
    assert first.title.startswith("Teraz tak")
    assert re.search(r"20–25 mm", first.sentence)
    assert re.search(r"\d[\d  ]*m³", first.sentence)
    section = r.section("nawadnianie")
    assert section.summary[0].text == "Teraz tak"
    assert any("BDOT10k" in s for s in section.sentences)
    assert any("pozwolenia wodnoprawnego" in s for s in section.sentences)


def test_irrigation_says_no_out_of_season_with_the_reason() -> None:
    r = report(GSM_TODAY)
    section = r.section("nawadnianie")
    assert section.summary[0].text == "Teraz nie"
    assert "21.III–30.IX" in section.sentences[0]
    first = next(a for a in r.actions if a.group == "nawadnianie")
    assert first.title.startswith("Teraz nie")


def test_out_of_season_residues_are_due_before_the_next_season() -> None:
    r = report(GSM_TODAY)
    mulch = next(a for a in r.actions if a.id == "mulczowanie")
    assert date(2026, 11, 21) <= mulch.due <= date(2027, 3, 20)
    assert "20.03.2027" in mulch.when


def test_section_seven_names_the_formula_it_stays_on() -> None:
    how = report().section("nawadnianie").how
    assert "FAO-56" in how and "strefie korzeni nie liczymy" in how


@pytest.mark.parametrize("params", PARCELS, ids=IDS)
@pytest.mark.parametrize("path", ["/raport", "/raport/druk"])
def test_soil_and_irrigation_sections_have_charts_and_no_placeholders(params: dict, path: str) -> None:
    page = client.get(f"{path}?{query(params, **({'widok': 'doradca'} if path == '/raport' else {}))}").text
    assert "Tu pojawi" not in page
    for sid in ("uprawa", "nawadnianie"):
        block = page[page.index(f'<section id="{sid}"') :]
        block = block[: block.index("</section>")]
        assert "<svg" in block, sid
        assert "Termin:" in block and "źródło:" in block, sid


def test_advisor_view_lists_the_team_proposals_of_both_sections() -> None:
    page = html(DOBRCZ, widok="doradca")
    for sid in ("uprawa", "nawadnianie"):
        block = page[page.index(f'<section id="{sid}"') :]
        block = block[: block.index("</section>")]
        assert "propozycja zespołu" in block, sid


def test_decade_summary_counts_stay_within_the_seasons_judged() -> None:
    sentence = report().section("uprawa").sentences[0]
    k, n = map(int, re.search(r"w (\d+) z (\d+) sezonów", sentence).groups())
    assert 0 <= k <= n <= 10


def test_crop_comparison_uses_the_same_soil_and_lists_other_crops() -> None:
    sentences = report().section("uprawa").sentences
    comparison = next(s for s in sentences if s.startswith("Te same dane pogodowe"))
    assert "zboża ozime" in comparison and re.search(r"\d z \d+", comparison)
