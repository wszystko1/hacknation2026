"""p77: the confidence bar with three zones and 100 dots; no "Trafność metody" in the farmer view; even gaps in the summary."""

from __future__ import annotations

import re

import pytest

from app.charts.confidence import confidence_for, confidence_view
from app.context import load_metrics
from tests.acceptance.helpers import DOBRCZ, GSM_TODAY, html, report

METRICS = load_metrics()


@pytest.mark.parametrize(
    ("margin", "zone", "word"),
    [(-5.0, "niepewne", "niepewny"), (-20.0, "raczej pewne", "raczej pewny"), (-47.0, "pewne", "pewny")],
)
def test_bar_and_dots_below_the_threshold(margin: float, zone: str, word: str) -> None:
    c = confidence_view(METRICS, margin)
    assert c is not None and c["zone_name"] == zone and c["sentence"].endswith(f"To wynik {word}.")
    share = METRICS[
        f"smsr.calibration.dg.{'m10_0' if margin == -5.0 else 'm25_m10' if margin == -20.0 else 'm50_m25'}.plus_share"
    ]
    assert c["n"] == min(99, round(100 * share)) and sum(c["dots"]) == c["n"] and len(c["dots"]) == 100
    assert f"w {c['n']} na 100" in c["sentence"] and c["label"] == f"Wiarygodność wyniku: {c['level']}"


def test_above_the_threshold_counts_the_agreeing_answer() -> None:
    c = confidence_view(METRICS, 5.0)
    assert c is not None and c["n"] == round(100 * (1 - METRICS["smsr.calibration.dg.0_10.plus_share"]))
    assert "nie wskazuje suszy" in c["sentence"] and c["zone_name"] == "niepewne"
    far = confidence_view(METRICS, 47.0)
    assert far is not None and far["level"] == "wysoka"
    assert confidence_view(METRICS, None) is None and confidence_view({}, 5.0) is None


def test_levels_and_marker() -> None:
    assert [confidence_view(METRICS, m)["level"] for m in (-5.0, -20.0, -47.0)] == [
        "średnia",
        "średnia",
        "wysoka",
    ]
    assert confidence_view(METRICS, -15.8)["marker"] == "16 mm poniżej progu"


def test_farmer_view_has_the_bar_and_no_old_measures() -> None:
    page = html(DOBRCZ, widok="rolnik")
    assert 'id="pasek-pewnosci"' in page and page.count('class="conf-grid"') == 1
    main = re.sub(
        r'<details class="b-row" id="wiersz-dla-doradcy".*?</details>',
        " ",
        page[page.index('<main id="tresc"') :],
        flags=re.S,
    )
    main = re.sub(r"<(script|style)\b.*?</\1>", " ", main, flags=re.S)
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", main))
    assert "Trafność metody" not in text and "zawsze częstsza odpowiedź" not in text
    folded = page[page.index('id="wiersz-dla-doradcy"') :]
    assert 'id="krzywa-kalibracji"' in folded and "Szczegóły zgodności z IUNG" in page


def test_dobrcz_confidence_matches_the_agreement_frame() -> None:
    r = report(DOBRCZ)
    c = confidence_for(r)
    assert c is not None and c["n"] == r.agreement.k_per_100 and c["level"] == "średnia"


def test_page_without_margin_still_renders() -> None:
    assert "Wiarygodność" in html(GSM_TODAY)
