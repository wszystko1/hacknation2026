"""Compare progi_dz_u_2019_739.csv with the text of the regulation PDF (Dz.U. 2019 poz. 739).

    uv run python -m app.drought.regulation_pdf      # downloads the PDF to data/raw/ when missing

The PDF comes from the ELI service of the Government Legislation Centre. Its text is read with `pdftotext -layout`
(poppler-utils); every table row is "<category> <14 cells>", the rows go group by group in the order of the annex.
Exit code 0 when all 784 cells agree. The app itself never reads the PDF.
"""

from __future__ import annotations

import csv
import re
import shutil
import subprocess
import sys
from pathlib import Path

from app.drought.thresholds import CSV_PATH

ROOT = Path(__file__).resolve().parents[2]
PDF_URL = "https://eli.gov.pl/api/acts/DU/2019/739/text.pdf"
PDF_PATH = ROOT / "data" / "raw" / "dz_u_2019_739" / "text.pdf"

# Crop groups in the order of the annex table (codes as in app.models.CropGroup).
ANNEX_ORDER = [
    "zboza_ozime",
    "zboza_jare",
    "kukurydza_ziarno",
    "kukurydza_kiszonka",
    "rzepak",
    "ziemniak",
    "burak_cukrowy",
    "chmiel",
    "tyton",
    "warzywa",
    "krzewy_owocowe",
    "drzewa_owocowe",
    "truskawki",
    "rosliny_straczkowe",
]
CATEGORIES = ["I", "II", "III", "IV"]
_CELL = r"(?:-?\d+|x|-|–)"
ROW = re.compile(rf"(?:^|\s)(I|II|III|IV)\s+({_CELL}(?:\s+{_CELL}){{13}})\s*$")

Cells = dict[tuple[str, str, int], str]


def fetch(path: Path = PDF_PATH) -> Path:
    """Download the regulation PDF once (data/raw is not committed)."""
    if path.exists():
        return path
    import httpx

    path.parent.mkdir(parents=True, exist_ok=True)
    r = httpx.get(PDF_URL, follow_redirects=True, timeout=60)
    r.raise_for_status()
    path.write_bytes(r.content)
    return path


def pdf_text(path: Path) -> str:
    if shutil.which("pdftotext") is None:
        raise RuntimeError("pdftotext (poppler-utils) is needed to read the PDF")
    out = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, check=True, text=True)
    return out.stdout


def parse(text: str) -> Cells:
    """The 14 x 4 x 14 cells of the annex: number as text ("-125"), "x" or "-"."""
    rows = [m.groups() for line in text.splitlines() if (m := ROW.search(line))]
    if len(rows) != len(ANNEX_ORDER) * len(CATEGORIES):
        raise ValueError(f"expected 56 table rows in the PDF text, found {len(rows)}")
    cells: Cells = {}
    for i, (category, values) in enumerate(rows):
        crop = ANNEX_ORDER[i // 4]
        if category != CATEGORIES[i % 4]:
            raise ValueError(f"row {i + 1}: expected category {CATEGORIES[i % 4]}, found {category}")
        for period, value in enumerate(values.split(), start=1):
            cells[(crop, category, period)] = "-" if value == "–" else value
    return cells


def read_csv(path: Path = CSV_PATH) -> Cells:
    with path.open(encoding="utf-8", newline="") as f:
        return {
            (r["crop"], r["soil_category"], int(r["period"])): r["threshold_mm"].strip()
            for r in csv.DictReader(f)
        }


def differences(table: Cells, regulation: Cells) -> list[str]:
    out = []
    for key in sorted(set(table) | set(regulation)):
        a, b = table.get(key), regulation.get(key)
        if a != b:
            out.append(f"{key}: CSV {a!r}, rozporządzenie {b!r}")
    return out


def main() -> int:
    regulation = parse(pdf_text(fetch()))
    diff = differences(read_csv(), regulation)
    for line in diff:
        print(line)
    print(f"{len(regulation)} komórek z PDF, różnic: {len(diff)}")
    return 1 if diff else 0


if __name__ == "__main__":
    sys.exit(main())
