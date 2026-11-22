"""The soil card: pure function, no network. Dobrcz: category II, sand 68%, clay 10%."""

from __future__ import annotations

from datetime import date

from app.models import CropGroup, PeriodBalance, SoilInfo, Verdict
from app.soil.card import NO_TEXTURE, build_card

DOBRCZ = SoilInfo(
    category="II", source="iung", words="gleba podatna na suszę (kat. II)",
    sand_pct=68.0, silt_pct=22.0, clay_pct=10.0, note="odczyt mapy IUNG w 8 z 9 punktów działki",
)  # fmt: skip


def verdict(threshold: float | None = -188.0) -> Verdict:
    period = PeriodBalance(
        n=4, start=date(2023, 4, 21), end=date(2023, 6, 20), precip_mm=60.0, et0_mm=264.0, kbw_mm=-204.0,
        threshold_mm=threshold, margin_mm=-16.0, complete=True, days=60,
    )  # fmt: skip
    return Verdict(
        state="below", badge="", kbw_mm=-204.0, threshold_mm=threshold, margin_mm=-16.0, period=period,
        sentence="", how="",
    )  # fmt: skip


def test_dobrcz_card_has_category_bar_paw_and_threshold():
    card = build_card(DOBRCZ, verdict(), CropGroup.ZBOZA_JARE)
    assert card is not None
    assert card.category_line.startswith("kategoria II: gleba lekka")
    assert card.share == "8 z 9 punktów działki"
    assert [s.key for s in card.segments] == ["sand", "silt", "clay"]
    assert abs(sum(s.width for s in card.segments) - 100) < 0.1
    assert card.paw and card.paw.mm > 0 and "szacunek" in card.paw.label
    assert "FAO-56" in card.paw.method
    assert "-188" in card.threshold.replace("−", "-") and "zbóż jarych" in card.threshold
    assert "dni parowania" in card.reserve
    assert "90%" in card.honesty
    assert not card.boundary


def test_no_soilgrids_gives_message_without_numbers():
    soil = DOBRCZ.model_copy(update={"sand_pct": None, "silt_pct": None, "clay_pct": None})
    card = build_card(soil, verdict(), CropGroup.ZBOZA_JARE)
    assert card is not None
    assert card.texture_note == NO_TEXTURE
    assert not card.segments and card.paw is None and not card.reserve and not card.how


def test_boundary_of_categories_is_mentioned():
    soil = DOBRCZ.model_copy(update={"note": "odczyt mapy IUNG w 6 z 9 punktów działki", "neighbour_category": "III"})
    card = build_card(soil, verdict(), CropGroup.ZBOZA_JARE)
    assert card is not None and "granicy kategorii" in card.boundary and "3 z 9" in card.boundary


def test_no_soil_at_all_gives_no_card():
    soil = SoilInfo(category=None, source="brak", words="brak")
    assert build_card(soil, verdict(), CropGroup.ZBOZA_JARE) is None
    assert build_card(None, None, CropGroup.ZBOZA_JARE) is None


def test_no_period_means_no_reserve_sentence():
    v = verdict().model_copy(update={"period": None, "threshold_mm": None})
    card = build_card(DOBRCZ, v, CropGroup.ZBOZA_JARE)
    assert card is not None and card.reserve == "" and card.threshold == "" and card.paw
