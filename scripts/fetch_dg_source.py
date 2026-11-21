"""Download the IUNG-PIB texts that print the Doroszewski-Górski formula into data/raw/dg_source/.

Run: `uv run python scripts/fetch_dg_source.py`. Two documents:
- the 2019 IUNG expertise on drought areas (gov.pl attachment), s. 6: the formula quoted from Doroszewski i in. 2012;
- Żyłowska, Kozyra 2023, Studia i Raporty IUNG-PIB 71(25), s. 65-76: the monthly formula we use (s. 67).
The 2012 text "Podstawy Systemu Monitoringu Suszy Rolniczej" is not freely downloadable; the script does not fetch it.
Each PDF is also converted to text with `pdftotext -layout` when that tool exists.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import httpx

SOURCES = {
    "gov_iung": "https://www.gov.pl/attachment/4b6eb509-6dec-4af6-902b-4eeb5312f36d",
    "zeszyt71_3": "https://www.iung.pl/sir/zeszyt71_3.pdf",
}
OUT = Path(__file__).resolve().parents[1] / "data" / "raw" / "dg_source"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    failed = 0
    for name, url in SOURCES.items():
        pdf = OUT / f"{name}.pdf"
        if not pdf.is_file():
            try:
                r = httpx.get(url, follow_redirects=True, timeout=60)
                r.raise_for_status()
                if not r.content.startswith(b"%PDF"):
                    raise ValueError("the answer is not a PDF")
                pdf.write_bytes(r.content)
            except (httpx.HTTPError, ValueError) as exc:
                print(f"{name}: {exc}", file=sys.stderr)
                failed += 1
                continue
        if shutil.which("pdftotext"):
            subprocess.run(["pdftotext", "-layout", str(pdf), str(pdf.with_suffix(".txt"))], check=False)
        print(pdf)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
