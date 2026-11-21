"""Download the PDFs the action catalogue quotes into data/raw/catalog/ (not committed).

    uv run python scripts/fetch_catalog_sources.py

`tests/test_catalog_quotes.py` checks every quote of the catalogue against the text of its PDF page and skips
when the file is missing. Page numbers in the catalogue are PDF page numbers (the first page of the file is 1),
not the numbers printed in the page footer.

"""

from __future__ import annotations

import shutil
import subprocess
import urllib.request
from pathlib import Path

RAW_DIR = Path("data/raw/catalog")

# address in the catalogue's source_url column -> file name in RAW_DIR
SOURCE_PDFS = {
    "https://woda.cdr.gov.pl/images/publikacje/Publikacje/Melioracje_retencja_wodna_e-poradnik_2025.pdf": (
        "cdr_melioracje_2025.pdf"
    ),
}


def page_text(pdf: Path, page: int) -> str:
    """Text of one PDF page (1-based) with whitespace collapsed and soft hyphens removed."""
    out = subprocess.run(
        ["pdftotext", "-f", str(page), "-l", str(page), str(pdf), "-"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return " ".join(out.replace("­", "").split())


def fetch_all() -> list[Path]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for url, name in SOURCE_PDFS.items():
        target = RAW_DIR / name
        if not target.exists():
            request = urllib.request.Request(url, headers={"User-Agent": "susza-katalog/1.0"})
            with urllib.request.urlopen(request, timeout=120) as response, target.open("wb") as handle:
                shutil.copyfileobj(response, handle)
        paths.append(target)
    return paths


if __name__ == "__main__":
    for path in fetch_all():
        print(f"{path} ({path.stat().st_size // 1024} KiB)")
