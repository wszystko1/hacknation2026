"""Every quote of the catalogue stands on the stated page of its PDF; skipped when the PDF is not downloaded.

Download with `uv run python scripts/fetch_catalog_sources.py`. Page numbers are PDF page numbers.
"""

from __future__ import annotations

import shutil

import pytest

from app.advice.catalog import load_catalog
from scripts.fetch_catalog_sources import RAW_DIR, SOURCE_PDFS, page_text

pytestmark = pytest.mark.skipif(shutil.which("pdftotext") is None, reason="pdftotext is not installed")


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
