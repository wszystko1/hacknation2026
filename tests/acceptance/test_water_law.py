"""K1: every retention or irrigation action that touches water has a Water Law formality with article, quote,
PDF page and date checked, or "sprawdź w Wodach Polskich" without an article number."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import pytest

from app.advice.legal import legal_note
from tests.acceptance.helpers import html

CSV_PATH = Path("app/advice/prawo_wodne.csv")
FORMALITIES = {
    "nic nie trzeba",
    "powiadomienie Wód Polskich",
    "zgłoszenie",
    "pozwolenie wodnoprawne",
    "sprawdź w Wodach Polskich",
}
# action id -> (formality, article fragment) as read from Dz.U. 2026 poz. 1335
EXPECTED = {
    "zastawka-istniejaca": ("nic nie trzeba", "art. 395 pkt 11"),
    "dreny-regulowany-odplyw": ("nic nie trzeba", "art. 395 pkt 12"),
    "przebudowa-rowu": ("powiadomienie Wód Polskich", "art. 395 pkt 15"),
    "niecka-przy-wyplywie": ("zgłoszenie", "art. 394 ust. 1 pkt 9"),
    "pobor-wody-nawadnianie": ("pozwolenie wodnoprawne", "art. 34 pkt 12"),
    "zastawka-nowa": ("powiadomienie Wód Polskich", "art. 395a"),  # a weir rebuilds the ditch to hold water
}


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_csv_rows_have_article_quote_page_and_date_or_check_with_wody_polskie() -> None:
    rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8")))
    assert {"action_id", "formality", "article", "quote", "pdf_page", "checked_on"} <= set(rows[0])
    for r in rows:
        assert r["formality"] in FORMALITIES, r
        date.fromisoformat(r["checked_on"])
        if r["formality"] == "sprawdź w Wodach Polskich":
            assert r["article"] == "", r
        else:
            assert r["article"].startswith("art. "), r
            assert len(r["quote"]) >= 20, r
            assert int(r["pdf_page"]) > 0, r


@pytest.mark.xfail(reason="not built yet", strict=False)
@pytest.mark.parametrize("action_id", sorted(EXPECTED))
def test_formality_of_each_water_action(action_id: str) -> None:
    formality, article = EXPECTED[action_id]
    note = legal_note(action_id)
    assert note.formality == formality
    assert article in note.article
    if formality == "sprawdź w Wodach Polskich":
        assert note.article == ""
    else:
        assert note.quote and note.pdf_page and note.checked_on


@pytest.mark.xfail(reason="not built yet", strict=False)
@pytest.mark.parametrize("action_id", ["zastawka-istniejaca", "zastawka-nowa", "przebudowa-rowu"])
def test_actions_changing_outflow_cite_art_234(action_id: str) -> None:
    assert any("art. 234 ust. 1" in e for e in legal_note(action_id).extra)


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_report_shows_the_formality_with_its_article_in_the_retention_section() -> None:
    page = html()
    start = page.index('id="retencja"')
    section = page[start : page.index("</section>", start)]
    assert "Prawo wodne" in section
    assert any(f in section for f in FORMALITIES)
    assert "art. " in section or "sprawdź w Wodach Polskich" in section


@pytest.mark.xfail(reason="not built yet", strict=False)
@pytest.mark.parametrize("action_id", ["zastawka-istniejaca", "zastawka-nowa"])
def test_weirs_warn_to_lower_the_water_level_in_wet_periods(action_id: str) -> None:
    warning = " ".join(legal_note(action_id).extra).lower()
    assert "obniż" in warning and "mokr" in warning, warning
