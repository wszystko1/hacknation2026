"""Weather 2001-2025 for the centroids of the evaluation communes, the input of the forecast validation.

    uv run python scripts/fetch_weather_history.py [--workers 3] [--refresh] [--limit N]

Precipitation comes from the nearest IMGW rain gauges and ET0 (FAO-56) from the nearest synoptic station, as in the
report; NASA POWER fills every day the stations do not cover (the IMGW archive we index starts in 2006, so 2001-2005
is NASA POWER alone). One file per commune: data/raw/weather_history/{teryt}.json, written whole or not at all, so an
interrupted run is resumed by running the command again. Needs data/raw/imgw (`python -m app.geodata imgw-sync`).
`make eval ONLY=forecast` reads these files and needs no network.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.geodata import imgw, weather  # noqa: E402
from app.geodata.errors import GeodataError  # noqa: E402

COMMUNES = ROOT / "demo" / "data" / "eval" / "gminy.csv"
OUT_DIR = ROOT / "data" / "raw" / "weather_history"
FIRST_DAY = date(2001, 1, 1)
LAST_DAY = date(2025, 12, 31)


def communes(path: Path = COMMUNES) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return [{**r, "lon": float(r["lon"]), "lat": float(r["lat"])} for r in csv.DictReader(f)]


def _power(lat: float, lon: float, attempts: int = 5) -> dict:
    """NASA POWER answers 429 under load: wait and ask again, longer each time."""
    for attempt in range(attempts):
        try:
            return weather._fetch_power(round(lat, 2), round(lon, 2), FIRST_DAY, LAST_DAY, None)[0]
        except GeodataError:
            if attempt == attempts - 1:
                raise
            time.sleep(15 * (attempt + 1))
    raise AssertionError("unreachable")


def snapshot(commune: dict) -> dict:
    lat, lon = commune["lat"], commune["lon"]
    days = [(FIRST_DAY + timedelta(days=i)).isoformat() for i in range((LAST_DAY - FIRST_DAY).days + 1)]
    precip: list[float | None] = [None] * len(days)
    et0: list[float | None] = [None] * len(days)
    codes_p, codes_e = [0] * len(days), [0] * len(days)
    gauge = imgw.lookup("precip", lat, lon, FIRST_DAY, LAST_DAY, max_km=weather.MAX_GAUGE_KM, max_stations=5)
    synop = imgw.lookup("et0", lat, lon, FIRST_DAY, LAST_DAY, max_km=weather.MAX_SYNOP_KM, max_stations=2)
    if gauge:
        weather._overlay(precip, codes_p, gauge["values"], 1, replace=True)
    if synop:
        weather._overlay(et0, codes_e, synop["values"], 1, replace=True)
    grid = _power(lat, lon)
    by_day = dict(zip(grid["dates"], zip(grid["precipitation_mm"], grid["et0_mm"], strict=True), strict=True))
    weather._overlay(precip, codes_p, [by_day.get(d, (None, None))[0] for d in days], 2, replace=False)
    weather._overlay(et0, codes_e, [by_day.get(d, (None, None))[1] for d in days], 2, replace=False)
    return {
        "teryt": commune["teryt"], "lat": lat, "lon": lon, "start": FIRST_DAY.isoformat(), "n": len(days),
        "imgw_share_precip": round(codes_p.count(1) / len(days), 4),
        "imgw_share_et0": round(codes_e.count(1) / len(days), 4),
        "precipitation_mm": precip, "et0_mm": et0,
    }  # fmt: skip


def write_whole(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, path)


def fetch_one(commune: dict, refresh: bool) -> str:
    path = OUT_DIR / f"{commune['teryt']}.json"
    if path.is_file() and not refresh:
        return "skipped"
    try:
        write_whole(path, snapshot(commune))
    except (GeodataError, ValueError) as exc:
        return f"FAILED {commune['teryt']} {commune['nazwa']}: {exc}"[:200]
    return "saved"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--refresh", action="store_true", help="download again although a file exists")
    ap.add_argument("--limit", type=int, default=0, help="only the first N communes")
    args = ap.parse_args(argv)
    if imgw.load_index() is None:
        print("IMGW index missing: run `uv run python -m app.geodata imgw-sync` first", file=sys.stderr)
        return 1
    todo = communes()[: args.limit or None]
    counts = {"saved": 0, "skipped": 0, "failed": 0}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i, msg in enumerate(pool.map(lambda c: fetch_one(c, args.refresh), todo), 1):
            counts["failed" if msg.startswith("FAILED") else msg] += 1
            if msg.startswith("FAILED"):
                print(msg, flush=True)
            if i % 20 == 0 or i == len(todo):
                print(f"{i}/{len(todo)} {counts}", flush=True)
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
