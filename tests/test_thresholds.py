"""The threshold table against the regulation: 14 crop groups x 4 soil categories x 14 periods."""

from __future__ import annotations

import shutil

import pytest

from app.drought import regulation_pdf
from app.drought.thresholds import threshold_cell, threshold_mm
from app.models import SOIL_CATEGORIES, CropGroup


def test_table_has_14_x_4_x_14_cells_in_regulation_form() -> None:
    cells = regulation_pdf.read_csv()
    groups = [c.value for c in CropGroup if c != CropGroup.INNA]
    assert len(cells) == 14 * 4 * 14
    assert set(cells) == {(g, s, n) for g in groups for s in SOIL_CATEGORIES for n in range(1, 15)}
    for value in cells.values():
        assert value in {"x", "-"} or (value.startswith("-") and value[1:].isdigit())


def test_raw_cell_tells_x_from_dash() -> None:
    assert threshold_cell(CropGroup.ZBOZA_JARE, "I", 10) == "x"
    assert threshold_cell(CropGroup.BURAK_CUKROWY, "I", 3) == "-"
    assert threshold_cell(CropGroup.ZBOZA_JARE, "I", 1) == "-125"
    assert threshold_cell(CropGroup.INNA, "I", 1) == ""
    assert threshold_mm(CropGroup.BURAK_CUKROWY, "II", 14) == -155


@pytest.mark.skipif(
    not regulation_pdf.PDF_PATH.exists() or shutil.which("pdftotext") is None,
    reason="regulation PDF not downloaded (uv run python -m app.drought.regulation_pdf) or no pdftotext",
)
def test_table_equals_the_regulation_pdf() -> None:
    regulation = regulation_pdf.parse(regulation_pdf.pdf_text(regulation_pdf.PDF_PATH))
    assert len(regulation) == 14 * 4 * 14
    assert regulation_pdf.differences(regulation_pdf.read_csv(), regulation) == []


def test_parser_reads_a_layout_row() -> None:
    dashes = "  ".join(["-"] * 14)
    rows = [f"        {c}        {dashes}" for _ in range(14) for c in SOIL_CATEGORIES]
    rows[5] = "Zboża jare       II        -144  -146  -149  -154  -161  -172  -188  -205  -226  x  x  x  x  x"
    text = "\n".join(rows)
    cells = regulation_pdf.parse(text)
    assert cells[("zboza_jare", "II", 1)] == "-144"
    assert cells[("zboza_jare", "II", 14)] == "x"
