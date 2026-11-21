"""Download the consolidated Water Law (Dz.U. 2026 poz. 1335) into data/raw/prawo_wodne/ (not committed).

    uv run python scripts/fetch_water_law.py                 # download
    uv run python scripts/fetch_water_law.py "art. 395a"     # print the PDF pages and lines that contain the phrase

`tests/test_legal.py` checks every quote of app/advice/prawo_wodne.csv against the text of its PDF page and skips
when the file is missing. Page numbers in the CSV are PDF page numbers (the first page of the file is 1).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

URL = "https://api.sejm.gov.pl/eli/acts/DU/2026/1335/text.pdf"
RAW_DIR = Path("data/raw/prawo_wodne")
PDF = RAW_DIR / "text.pdf"


def normal(text: str) -> str:
    """Whitespace collapsed, soft hyphens removed, non-breaking hyphens and spaces made plain."""
    return " ".join(text.replace("­", "").replace("‑", "-").replace("\xa0", " ").split())


def page_text(pdf: Path, page: int) -> str:
    """Text of one PDF page (1-based), normalised."""
    out = subprocess.run(
        ["pdftotext", "-f", str(page), "-l", str(page), str(pdf), "-"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return normal(out)


def page_count(pdf: Path) -> int:
    info = subprocess.run(["pdfinfo", str(pdf)], check=True, capture_output=True, text=True).stdout
    return int(next(line.split()[1] for line in info.splitlines() if line.startswith("Pages:")))


def fetch() -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if not PDF.exists():
        request = urllib.request.Request(URL, headers={"User-Agent": "susza-prawo-wodne/1.0"})
        with urllib.request.urlopen(request, timeout=120) as response, PDF.open("wb") as handle:
            shutil.copyfileobj(response, handle)
    return PDF


def find(pdf: Path, phrase: str) -> list[tuple[int, str]]:
    """(PDF page, text of the page around the phrase) for every page that contains the phrase."""
    hits: list[tuple[int, str]] = []
    needle = normal(phrase).lower()
    for page in range(1, page_count(pdf) + 1):
        text = page_text(pdf, page)
        at = text.lower().find(needle)
        if at >= 0:
            hits.append((page, text[max(0, at - 40) : at + 240]))
    return hits


if __name__ == "__main__":
    path = fetch()
    if len(sys.argv) > 1:
        for page, snippet in find(path, " ".join(sys.argv[1:])):
            print(f"[PDF page {page}] ...{snippet}...")
    else:
        print(f"{path} ({path.stat().st_size // 1024} KiB, {page_count(path)} pages)")
