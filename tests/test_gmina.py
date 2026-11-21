"""The commune section: one SMSR object, measures beside the trivial answer, no empty cells."""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.fmt import pct
from tests.acceptance.helpers import DOBRCZ, GSM_TODAY, html

SMSR = json.loads((Path(__file__).resolve().parents[1] / "metrics.json").read_text(encoding="utf-8"))["smsr"]


def _section(page: str) -> str:
    start = page.index('id="gmina"')
    return page[start : page.index("</section>", start)]


def test_section_route_has_no_dash_cell_and_shows_metrics_json_numbers() -> None:
    section = html(DOBRCZ, path="/raport/sekcja/gmina")
    assert not re.search(r"<(td|th|b)[^>]*>\s*–\s*</", section)
    assert pct(SMSR["accuracy"], 1) in section
    assert pct(SMSR["accuracy_majority"], 1) in section
    assert "zawsze częstsza odpowiedź" in section


def test_frame_states_both_scores_per_100_cases() -> None:
    page = html(DOBRCZ)
    frame = re.search(r'id="zgodnosc-ramka".*?</div>\s*</div>', page, flags=re.S)
    assert frame
    text = re.sub(r"<[^>]+>", " ", frame.group(0))
    assert re.search(r"w \d+ na 100 przypadków; odpowiedź „zawsze częstsza odpowiedź” w \d+ na 100", text)


def test_report_and_print_have_no_placeholder_in_section_2() -> None:
    for params in (DOBRCZ, GSM_TODAY):
        for path in ("/raport", "/raport/druk"):
            section = _section(html(params, path=path))
            assert "Tu pojawi" not in section
            assert "tabel SMSR jeszcze nie wczytujemy" not in section


def test_smsr_row_and_section_share_one_result() -> None:
    page = html(DOBRCZ)
    assert 'id="wiersz-smsr"' in page
    row = page[page.index('id="wiersz-smsr"') :][:600]
    assert "zagrożone" in row
    assert "zagrożone" in _section(page)
    assert "tabel SMSR jeszcze nie wczytujemy" not in page


def test_short_measurement_is_one_sentence_not_an_empty_table() -> None:
    from types import SimpleNamespace

    from app.models import Agreement
    from app.sections.gmina import build

    ctx = SimpleNamespace(
        metrics={"smsr.n_gmina_years": 120},
        agreement=Agreement(available=False, sentence=""),
        smsr=None,
    )
    section = build(ctx)  # type: ignore[arg-type]
    assert section.reason == "Pomiar zgodności: w toku, 120 z 300 gmino-lat."
    assert section.state == "missing"
