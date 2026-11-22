"""Source kinds, research sources and risks of the action catalogue.

Every row says what kind of source stands behind it: a description of the practice, a study with a number, or a team
proposal. A row that claims a publication names it with an address; a row without one says it is our proposal. The
research quotes are checked against the PDF text when the file is in `data/raw/catalog_research/` (skipped otherwise).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path

import pytest

from app.advice.catalog import RISK_KINDS, SOURCE_KINDS, CatalogRow, load_catalog

RESEARCH_DIR = Path("data/raw/catalog_research")
RESEARCH_PDFS = {
    "https://www.nwrm.eu/sites/default/files/nwrm_ressources/a2_-_buffer_strips_and_hedges.pdf": "nwrm_a2.pdf",
}
# Publications whose page is not quoted in the row: the FAO-56 method chapter and an article of the Water Law act.
PUBLICATION_WITHOUT_QUOTE = {"nawadnianie-termin-fao56", "pobor-wody-nawadnianie"}
FORBIDDEN_WORDS = re.compile(r"dopłat|wniosek|wniosk", re.IGNORECASE)


def _normal(text: str) -> str:
    return " ".join(text.replace("­", "").replace("‑", "-").split()).lower()


def test_every_row_has_a_source_kind() -> None:
    for row in load_catalog().values():
        assert row.source_kind in SOURCE_KINDS, row.action_id


def test_a_row_has_a_publication_or_says_it_is_a_team_proposal() -> None:
    for row in load_catalog().values():
        if row.source_kind == "propozycja zespołu":
            assert not row.has_full_source() and not row.has_research_source(), row.action_id
            assert "propozycja zespołu" in row.source_doc, row.action_id
            continue
        assert row.source_doc.strip() and "propozycja" not in row.source_doc, row.action_id
        assert row.source_url.startswith("http"), row.action_id
        if row.action_id in PUBLICATION_WITHOUT_QUOTE:
            continue
        assert row.has_full_source() or row.has_research_source(), row.action_id


def test_a_study_with_a_number_has_a_quote_and_a_page() -> None:
    studies = [r for r in load_catalog().values() if r.source_kind == "badanie z liczbą"]
    assert studies
    for row in studies:
        assert row.has_full_source() or row.has_research_source(), row.action_id
        use_research = row.has_research_source()
        quote = row.research_quote if use_research else row.source_quote
        page = row.research_page if use_research else row.source_page
        assert re.search(r"\d", quote), (row.action_id, "a study with a number quotes the number")
        assert re.search(r"\d", page), row.action_id


def test_rows_count_by_kind() -> None:
    counts = Counter(r.source_kind for r in load_catalog().values())
    assert counts == {"opis praktyki": 17, "badanie z liczbą": 5, "propozycja zespołu": 4}


def test_the_research_columns_are_all_set_or_all_empty() -> None:
    for row in load_catalog().values():
        filled = [
            row.research_doc,
            row.research_url,
            row.research_page,
            row.research_quote,
            row.research_says,
        ]
        assert all(f.strip() for f in filled) or not any(f.strip() for f in filled), row.action_id
        assert (
            len(row.research_quote.split(" | ")) == len(row.research_page.split("; "))
            or not row.research_quote
        ), row.action_id


def test_runoff_actions_cite_the_buffer_strip_research_with_six_metres() -> None:
    catalog = load_catalog()
    for action_id in ("pas-trawy-przy-wyplywie", "pas-buforowy-wzdluz-rowu"):
        row = catalog[action_id]
        assert row.source_kind == "badanie z liczbą", action_id
        assert "NWRM A02" in row.research_doc and "2005" in row.research_doc, action_id
        assert "78%" in row.research_quote and "6 m" in row.research_says, action_id
        assert row.effect_low is None, "no effect number for a parcel from a single field experiment"


def test_the_ponds_and_the_contour_banks_have_a_research_source() -> None:
    catalog = load_catalog()
    for action_id in ("niecka-przy-wyplywie", "ochrona-zbiornika", "miedza-w-poprzek-stoku"):
        assert catalog[action_id].has_research_source(), action_id


def test_contour_tillage_stays_a_team_proposal_with_its_reason() -> None:
    row = load_catalog()["uprawa-w-poprzek-stoku"]
    assert row.source_kind == "propozycja zespołu" and row.confidence == "propozycja zespołu"
    assert any(r.kind == "opinia" for r in row.risks)


def _pdf_page(pdf: Path, page: int) -> str:
    out = subprocess.run(
        ["pdftotext", "-f", str(page), "-l", str(page), str(pdf), "-"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return _normal(out)


PDF_ROWS = [r for r in load_catalog().values() if r.research_url in RESEARCH_PDFS]


@pytest.mark.skipif(shutil.which("pdftotext") is None, reason="pdftotext is not installed")
@pytest.mark.parametrize("row", PDF_ROWS, ids=lambda r: r.action_id)
def test_research_quotes_are_on_their_pdf_pages(row: CatalogRow) -> None:
    pdf = RESEARCH_DIR / RESEARCH_PDFS[row.research_url]
    if not pdf.exists():
        pytest.skip(f"{pdf} not downloaded")
    for quote, page in zip(row.research_quote.split(" | "), row.research_page.split("; "), strict=True):
        assert _normal(quote) in _pdf_page(pdf, int(page)), (row.action_id, page)


def test_every_row_has_risks_with_a_source_and_a_kind() -> None:
    for row in load_catalog().values():
        assert 1 <= len(row.risks) <= 2, row.action_id
        assert row.not_when and row.next_step, row.action_id
        for risk in row.risks:
            assert risk.kind in RISK_KINDS, (row.action_id, risk.kind)
            assert risk.text and risk.source, (row.action_id, risk.text)


def test_a_risk_without_a_source_is_labelled_an_opinion() -> None:
    kinds = Counter()
    for row in load_catalog().values():
        for risk in row.risks:
            kinds[risk.kind] += 1
            if risk.source.startswith("bez źródła"):
                assert risk.kind == "opinia", (row.action_id, risk)
    assert kinds["opinia"] >= 1 and kinds["przepis prawny"] >= 1 and kinds["badanie"] >= 1


def test_text_for_the_user_avoids_support_scheme_words() -> None:
    for row in load_catalog().values():
        texts = [row.title, row.sentence, row.not_when, row.next_step]
        texts += [r.text for r in row.risks] + [r.source for r in row.risks]
        for text in texts:
            assert not FORBIDDEN_WORDS.search(text), (row.action_id, text)


def test_the_intercrop_window_is_not_given_as_the_agronomic_optimum() -> None:
    row = load_catalog()["miedzyplon"]
    window = [r for r in row.risks if "1.07" in r.source]
    assert window and "nie optimum agrotechniczne" in window[0].source


def test_drain_regulator_is_a_notification_and_backing_up_water_risks_the_neighbours() -> None:
    catalog = load_catalog()
    drains = catalog["dreny-regulowany-odplyw"]
    assert "395 pkt 16" in drains.legal_article and "395a" in drains.legal_article
    assert any("395a" in r.text and r.kind == "przepis prawny" for r in drains.risks)
    for action_id in ("zastawka-istniejaca", "zastawka-nowa", "przebudowa-rowu"):
        assert any("art. 234" in r.source and r.kind == "przepis prawny" for r in catalog[action_id].risks), (
            action_id
        )
