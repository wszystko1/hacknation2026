"""K2: the balance by the definition of Dz.U. 2019 poz. 739, soil category, SMSR row, sources with times."""

from __future__ import annotations

import csv
from datetime import date, timedelta

import pytest

from app.drought.kbw import assess
from app.drought.thresholds import CSV_PATH, threshold_mm
from app.models import BADGE_ABOVE, BADGE_BELOW, DISCLAIMER, CropGroup
from tests.acceptance.helpers import DOBRCZ, report


def weather(start: date, end: date, rain: float, et0: float) -> tuple[list[str], list[float], list[float]]:
    days = [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]
    return days, [rain] * len(days), [et0] * len(days)


def test_threshold_table_has_14_groups_4_categories_14_periods() -> None:
    rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8")))
    keys = {(r["crop"], r["soil_category"], int(r["period"])) for r in rows}
    groups = {c.value for c in CropGroup} - {"inna"}
    assert len(rows) == len(keys) == 14 * 4 * 14
    assert {k[0] for k in keys} == groups
    for r in rows:
        assert r["threshold_mm"] in {"-", "x"} or float(r["threshold_mm"]) < 0


def test_thresholds_match_the_regulation_on_known_cells() -> None:
    assert threshold_mm(CropGroup.ZBOZA_JARE, "I", 1) == -125
    assert threshold_mm(CropGroup.ZBOZA_JARE, "IV", 1) == -194
    assert threshold_mm(CropGroup.ZBOZA_OZIME, "IV", 9) == -306
    assert threshold_mm(CropGroup.ROSLINY_STRACZKOWE, "I", 14) == -176
    assert threshold_mm(CropGroup.KUKURYDZA_ZIARNO, "I", 1) is None  # "x"
    assert threshold_mm(CropGroup.BURAK_CUKROWY, "I", 5) is None  # "-": not recommended on this soil


def test_dry_season_is_below_threshold_with_fixed_badge_and_sentence() -> None:
    d, p, e = weather(date(2023, 3, 1), date(2023, 7, 20), rain=0.5, et0=4.0)
    v = assess(d, p, e, date(2023, 7, 20), CropGroup.ZBOZA_JARE, "I")
    assert v.state == "below"
    assert v.badge == BADGE_BELOW
    assert v.disclaimer == DISCLAIMER
    assert v.margin_mm is not None and v.margin_mm < 0
    assert v.period is not None and v.period.complete
    assert v.margin_mm == min(p.margin_mm for p in v.periods if p.margin_mm is not None)
    assert v.sentence.startswith("W tych 60 dniach wyparowało o ")
    assert "poniżej progu suszy" in v.sentence


def test_wet_season_is_above_threshold() -> None:
    d, p, e = weather(date(2023, 3, 1), date(2023, 7, 20), rain=3.0, et0=3.0)
    v = assess(d, p, e, date(2023, 7, 20), CropGroup.ZBOZA_JARE, "IV")
    assert v.state == "above"
    assert v.badge == BADGE_ABOVE


def test_before_20_may_the_period_is_still_running_without_badge() -> None:
    d, p, e = weather(date(2023, 3, 1), date(2023, 5, 1), rain=0.0, et0=4.0)
    v = assess(d, p, e, date(2023, 5, 1), CropGroup.ZBOZA_JARE, "I")
    assert v.state == "running"
    assert v.badge == ""
    assert "trwa" in v.note


def test_november_is_out_of_monitoring_and_shows_last_season() -> None:
    d, p, e = weather(date(2026, 3, 1), date(2026, 11, 21), rain=1.0, et0=2.0)
    v = assess(d, p, e, date(2026, 11, 21), CropGroup.ROSLINY_STRACZKOWE, "II")
    assert v.state == "out_of_season"
    assert v.season_year == 2026
    assert v.kbw_mm is not None


def test_other_crop_gives_the_balance_without_a_legal_threshold() -> None:
    d, p, e = weather(date(2023, 3, 1), date(2023, 7, 20), rain=0.5, et0=4.0)
    v = assess(d, p, e, date(2023, 7, 20), CropGroup.INNA, "I")
    assert v.state == "no_threshold"
    assert v.badge == ""
    assert v.kbw_mm is not None


def test_sources_table_has_time_and_state_and_gaps_have_reasons() -> None:
    r = report()
    keys = {s.key for s in r.sources}
    assert {"parcel", "weather", "ortho", "soil", "terrain", "water", "satellite"} <= keys
    for s in r.sources:
        assert s.status in {"ok", "fallback", "missing", "waiting", "copy"}
        if s.status == "missing":
            assert s.reason
    assert r.data_copy == "kopia danych z 21.11.2026"


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_soil_category_comes_from_iung_layer_or_soilgrids() -> None:
    r = report()
    assert r.soil.category in {"I", "II", "III", "IV"}
    assert r.soil.source in {"iung", "soilgrids"}
    assert r.verdict.threshold_mm is not None
    assert r.verdict.state in {"below", "above"}


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_texture_near_a_class_boundary_gives_the_neighbour_category() -> None:
    from app.soil.texture import category_from_texture

    category, neighbour = category_from_texture(sand_pct=95.0, silt_pct=4.0, clay_pct=1.0)
    assert category == "I"
    assert neighbour is None
    category, neighbour = category_from_texture(sand_pct=10.0, silt_pct=40.0, clay_pct=50.0)
    assert category == "IV"
    edge = [category_from_texture(sand_pct=s, silt_pct=90.0 - s, clay_pct=10.0) for s in range(30, 90)]
    assert any(n is not None for _, n in edge)


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_smsr_row_for_the_commune_period_crop_and_soil() -> None:
    r = report()
    assert r.smsr.state == "ok"
    assert r.smsr.commune == "Dobrcz"
    assert r.smsr.year == 2023
    assert r.smsr.period_n == r.verdict.period.n
    assert r.smsr.soil_category == r.soil.category
    assert r.smsr.symbol in {"+", "-", "x", "#", "*", "n"}
    assert r.smsr.words


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_smsr_parser_reads_symbols_and_area_share() -> None:
    from pathlib import Path

    from app.smsr.parser import parse_commune_page

    page = Path("tests/fixtures/smsr/2023_0403043.html").read_text(encoding="utf-8")
    table = parse_commune_page(page)
    assert table.commune == "Koronowo"
    assert table.year == 2023
    cell = table.symbol("Zboża jare", "I", 7)
    assert cell in {"+", "-", "x", "#", "*", "n"}
    assert table.area_share_pct("Zboża jare", 7) is None or 0 <= table.area_share_pct("Zboża jare", 7) <= 100


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_ten_seasons_of_history_from_the_same_code() -> None:
    r = report()
    history = r.section("historia")
    assert history.state == "ready"
    assert "z 10" in "".join(p.text for p in history.summary) or "z 9" in "".join(
        p.text for p in history.summary
    )
    assert history.chart_svg.startswith("<svg")


def test_advisor_can_set_the_soil_category() -> None:
    r = report(DOBRCZ, gleba="IV")
    assert r.soil.category == "IV"
    assert r.soil.source == "doradca"
    assert r.verdict.threshold_mm is not None
