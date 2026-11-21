"""Every quote of the catalogue stands on the stated page of its PDF; skipped when the PDF is not downloaded.

Download with `uv run python scripts/fetch_catalog_sources.py`. Page numbers are PDF page numbers.
"""

from __future__ import annotations

import shutil

import pytest

from app.advice.catalog import load_catalog
from scripts.fetch_catalog_sources import ACPF_PDF, RAW_DIR, SOURCE_PDFS, page_text

pytestmark = pytest.mark.skipif(shutil.which("pdftotext") is None, reason="pdftotext is not installed")

ACPF_NAMES = {
    "row-zadarniony": "grassed waterway",
    "pas-konturowy": "contour buffer",
    "dreny-regulowany-odplyw": "drainage water management",
}


def _normal(text: str) -> str:
    return " ".join(text.replace("­", "").replace("‑", "-").split()).lower()


QUOTED = [r for r in load_catalog().values() if r.source_quote]


def test_every_quoted_source_has_a_downloadable_pdf() -> None:
    for row in QUOTED:
        assert row.source_url in SOURCE_PDFS, (row.action_id, row.source_url)
        assert row.source_page.isdigit(), (row.action_id, row.source_page)


@pytest.mark.parametrize("row", QUOTED, ids=lambda r: r.action_id)
def test_quote_is_on_the_stated_page(row) -> None:  # noqa: ANN001
    pdf = RAW_DIR / SOURCE_PDFS[row.source_url]
    if not pdf.exists():
        pytest.skip(f"{pdf} not downloaded")
    assert _normal(row.source_quote) in _normal(page_text(pdf, int(row.source_page))), row.action_id


@pytest.mark.parametrize("action_id", sorted(ACPF_NAMES))
def test_acpf_page_names_the_practice(action_id: str) -> None:
    if not ACPF_PDF.exists():
        pytest.skip(f"{ACPF_PDF} not provided")
    row = load_catalog()[action_id]
    assert row.source_page.isdigit(), (action_id, "page of the ACPF manual")
    assert ACPF_NAMES[action_id] in _normal(page_text(ACPF_PDF, int(row.source_page))), action_id
