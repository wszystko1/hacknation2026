"""Water Law notes: the loader refuses incomplete rows, every quote stands on its PDF page, and the report cites them."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.advice.legal import CHECK, CSV_PATH, legal_note, load_notes
from scripts.fetch_water_law import PDF, page_text
from tests.acceptance.helpers import DOBRCZ, GSM_TODAY, report

HEADER = "action_id,formality,article,quote,pdf_page,checked_on,extra\n"
WATER_ACTIONS = [
    "zastawka-istniejaca",
    "zastawka-nowa",
    "dreny-regulowany-odplyw",
    "przebudowa-rowu",
    "niecka-przy-wyplywie",
    "pobor-wody-nawadnianie",
]


def _csv(tmp_path: Path, *lines: str) -> Path:
    path = tmp_path / "prawo_wodne.csv"
    path.write_text(HEADER + "".join(line + "\n" for line in lines), encoding="utf-8")
    return path


def test_unknown_action_says_check_with_wody_polskie_and_no_article() -> None:
    note = legal_note("action-without-a-row")
    assert note.formality == CHECK and note.article == "" and note.quote == ""


def test_row_without_quote_is_refused(tmp_path: Path) -> None:
    path = _csv(tmp_path, "x,zgłoszenie,art. 394 ust. 1 pkt 9,,12,2026-11-21,")
    with pytest.raises(ValueError, match="article, quote and PDF page"):
        load_notes(path)


def test_check_row_with_article_is_refused(tmp_path: Path) -> None:
    path = _csv(tmp_path, f"x,{CHECK},art. 33,,,2026-11-21,")
    with pytest.raises(ValueError, match="without an article"):
        load_notes(path)


def test_complete_row_and_extra_are_read(tmp_path: Path) -> None:
    path = _csv(
        tmp_path,
        'x,zgłoszenie,art. 394 ust. 1 pkt 9,"a quote of some length",12,2026-11-21,art. 234 ust. 1 | zgoda sąsiada',
        f"y,{CHECK},,,,2026-11-21,",
    )
    notes = load_notes(path)
    assert notes["x"].pdf_page == 12 and notes["x"].extra == ["art. 234 ust. 1", "zgoda sąsiada"]
    assert notes["y"].article == "" and notes["y"].pdf_page is None


@pytest.mark.skipif(shutil.which("pdftotext") is None, reason="pdftotext is not installed")
@pytest.mark.parametrize("action_id", sorted(load_notes()) or ["none"])
def test_quote_is_on_the_stated_pdf_page(action_id: str) -> None:
    if not PDF.exists():
        pytest.skip(f"{PDF} not downloaded")
    note = load_notes().get(action_id)
    if note is None or not note.quote:
        pytest.skip("no quote to check")
    assert note.pdf_page is not None
    assert " ".join(note.quote.split()).lower() in page_text(PDF, note.pdf_page).lower(), action_id


@pytest.mark.xfail(reason="the CSV rows with quotes are not filled in yet", strict=False)
def test_every_water_action_has_a_row() -> None:
    rows = load_notes(CSV_PATH)
    assert set(WATER_ACTIONS) <= set(rows), sorted(set(WATER_ACTIONS) - set(rows))


@pytest.mark.parametrize("params", [DOBRCZ, GSM_TODAY], ids=["dobrcz", "gsm"])
def test_report_formalities_cite_an_article_with_a_quote_or_say_to_check(params: dict) -> None:
    actions = [a for a in report(params).actions if a.legal is not None]
    assert actions, "the report has no action with a formality"
    for a in actions:
        note = a.legal
        assert note is not None
        if note.formality == CHECK:
            assert note.article == ""
        else:
            assert note.article.startswith("art. ") and note.quote and note.pdf_page, a.id
