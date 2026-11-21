"""Archive of SMSR commune pages for the agreement measurement.

    uv run python scripts/fetch_smsr.py [--years 2020-2026] [--pause 0.5]

For every commune of demo/data/eval/gminy.csv and every year it saves
data/raw/smsr/{year}_{teryt}.html and a sidecar {year}_{teryt}.json (download time, seconds).
A page is checked with the parser before it is saved; a file is written whole or not at all, so an
interrupted run is resumed by running the command again: pages already on disk are skipped.
~200 communes x 7 years = 1400 requests: 0.5 s pause plus 0.3-0.8 s per page, so 30-40 minutes.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.smsr.parser import SmsrPageError, parse_commune_page  # noqa: E402

URL = "https://susza.iung.pulawy.pl/wykazy/{year},{teryt}/"
COMMUNES = ROOT / "demo" / "data" / "eval" / "gminy.csv"
OUT_DIR = ROOT / "data" / "raw" / "smsr"
FIRST_YEAR, LAST_YEAR = 2020, 2026


def communes(path: Path = COMMUNES) -> list[str]:
    with path.open(encoding="utf-8") as f:
        return [row["teryt"] for row in csv.DictReader(f)]


def write_whole(path: Path, text: str) -> None:
    """Write through a temporary file, so a killed run never leaves half a page."""
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def fetch_page(client: httpx.Client, year: int, teryt: str, attempts: int = 3) -> tuple[str, float] | None:
    """The page text and the seconds it took; None after `attempts` failures or for a page that is not a table."""
    for attempt in range(attempts):
        started = time.monotonic()
        try:
            resp = client.get(URL.format(year=year, teryt=teryt), timeout=30)
        except httpx.HTTPError:
            resp = None
        if resp is not None and resp.status_code == 200:
            try:
                parse_commune_page(resp.text)
            except SmsrPageError:
                return None
            return resp.text, time.monotonic() - started
        if resp is not None and resp.status_code == 404:
            return None
        time.sleep(2 * (attempt + 1))
    return None


def run(
    client: httpx.Client,
    teryts: list[str],
    years: range,
    out_dir: Path = OUT_DIR,
    pause_s: float = 0.5,
) -> dict[str, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    counts = {"downloaded": 0, "already_there": 0, "failed": 0}
    failed: list[str] = []
    todo = [(y, t) for t in teryts for y in years]
    for i, (year, teryt) in enumerate(todo, start=1):
        path = out_dir / f"{year}_{teryt}.html"
        if path.exists():
            counts["already_there"] += 1
            continue
        time.sleep(pause_s)
        got = fetch_page(client, year, teryt)
        if got is None:
            counts["failed"] += 1
            failed.append(f"{year}_{teryt}")
            continue
        text, elapsed = got
        meta = {
            "retrieved_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "elapsed_s": round(elapsed, 2),
        }
        write_whole(path.with_suffix(".json"), json.dumps(meta))
        write_whole(path, text)
        counts["downloaded"] += 1
        if i % 50 == 0:
            print(f"{i}/{len(todo)} {counts}", file=sys.stderr, flush=True)
    write_whole(out_dir / "failed.txt", "\n".join(failed))
    return counts


def parse_years(text: str) -> range:
    first, _, last = text.partition("-")
    return range(int(first), int(last or first) + 1)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--years", default=f"{FIRST_YEAR}-{LAST_YEAR}")
    ap.add_argument("--pause", type=float, default=0.5)
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    ap.add_argument("--communes", type=Path, default=COMMUNES)
    args = ap.parse_args(argv)
    headers = {"User-Agent": "susza-raport/0.1 (research archive)"}
    with httpx.Client(headers=headers, follow_redirects=True) as client:
        counts = run(client, communes(args.communes), parse_years(args.years), args.out, args.pause)
    print(counts)
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
