"""No "Tu pojawi się…" text reaches the farmer, the advisor or the print view: what is not computed yet
is one explicit sentence "Brak: <what>, bo <why>"."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.acceptance.helpers import DOBRCZ, GSM_TODAY, html, report

ROUTES = [
    ("/raport", {}),
    ("/raport", {"widok": "doradca"}),
    ("/raport/druk", {}),
]
PARCELS = [DOBRCZ, GSM_TODAY]
APP_DIR = Path(__file__).resolve().parent.parent / "app"

EMPTY_PARAGRAPH = re.compile(r'<p class="empty">(.*?)</p>', re.S)
BRAK_SENTENCE = re.compile(r"Brak:[^<]*")


def test_source_has_no_placeholder_sentences() -> None:
    hits = [
        f"{path.relative_to(APP_DIR.parent)}:{n}"
        for path in APP_DIR.rglob("*")
        if path.suffix in {".py", ".html", ".js"}
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if "Tu pojawi" in line
    ]
    assert hits == []


@pytest.mark.parametrize("params", PARCELS, ids=["dobrcz", "gora-swietej-malgorzaty"])
@pytest.mark.parametrize(("path", "extra"), ROUTES, ids=["rolnik", "doradca", "druk"])
def test_no_placeholder_and_every_gap_names_its_reason(path: str, extra: dict, params: dict) -> None:
    page = html(params, path=path, **extra)
    assert "Tu pojawi" not in page
    assert "Tu pojawią" not in page
    if path == "/raport" and not extra:
        # The farmer screen lists what is missing in one closing line instead of boxes.
        assert "Brak: " not in page
        return
    gaps = BRAK_SENTENCE.findall(page)
    assert gaps, "the skeleton parts must say what is missing"
    for gap in gaps:
        assert re.search(r"\bbo\b", gap), gap
    for paragraph in EMPTY_PARAGRAPH.findall(page):
        assert paragraph.strip().startswith("Brak:"), paragraph
        assert re.search(r"\bbo\b", paragraph), paragraph


def test_demo_report_route_has_no_placeholder() -> None:
    page = html(DOBRCZ)
    assert "Tu pojawi" not in page and "Tu pojawią" not in page


def test_missing_parts_carry_the_gap_sentence_in_the_report() -> None:
    r = report()
    assert r.crop_condition.words.startswith("Brak:") and " bo " in r.crop_condition.words
    # The exceedance forecast is computed now, so it is a value, not a gap.
    assert r.forecast.state == "ok" and not r.forecast.sentence.startswith("Brak:")
    # SMSR agreement is measured now (metrics.json), so it is a value, not a gap.
    assert r.agreement.available and not r.agreement.sentence.startswith("Brak:")
    # The commune's SMSR row is read now (frozen demo page), so it is a value, not a gap.
    assert r.smsr.state == "ok"
    assert r.smsr.commune == "Dobrcz" and r.smsr.words
    assert "Brak" not in r.smsr.words and r.smsr.reason == ""
    for section in r.sections:
        if section.state == "missing" and section.id != "zrodla":
            assert section.reason.startswith("Brak:") and " bo " in section.reason, section.id


def test_action_one_stays_with_a_sentence_a_reason_for_no_place_and_a_seasonal_term() -> None:
    r = report()
    a1 = r.action_1
    assert a1 is not None and a1.n == 1
    assert not a1.sentence.startswith("Brak:") and "{" not in a1.sentence
    assert a1.place is None and a1.no_place_reason.startswith("brak miejsca na działce, bo ")
    assert a1.when and not a1.when.startswith("Brak:")
    # Tillage and irrigation actions are computed from indicators now: none is a placeholder.
    for a in (a for a in r.actions if a.group in {"uprawa", "nawadnianie"}):
        assert "Tu pojawi" not in a.sentence and not a.sentence.startswith("Brak:"), a.id
