"""Weather 2020 to today for the centroids of the evaluation communes, by the code the app uses.

    uv run python scripts/fetch_commune_weather.py [--workers 3] [--refresh] [--limit N]

For every commune of demo/data/eval/gminy.csv it calls `app.geodata.weather.fetch_weather` (same provider order,
same ET0, same cache as the report) and saves data/raw/commune_weather/{teryt}.json with the daily series from
1 January 2020: precipitation, FAO-56 ET0, mean temperature and sunshine (the inputs of the second ET variant).
Next to it goes the NASA POWER grid alone (precipitation and ET0), the reference line "grid only".
A file is written whole or not at all; communes already on disk are skipped, so an interrupted run is resumed
by running the command again. `make eval ONLY=smsr` reads these files and needs no network.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.geodata import weather  # noqa: E402
from app.geodata.errors import GeodataError  # noqa: E402

COMMUNES = ROOT / "demo" / "data" / "eval" / "gminy.csv"
OUT_DIR = ROOT / "data" / "raw" / "commune_weather"
FIRST_DAY = date(2020, 1, 1)


def communes(path: Path = COMMUNES) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return [{**r, "lon": float(r["lon"]), "lat": float(r["lat"])} for r in csv.DictReader(f)]


def _tail(values: list, start: int) -> list:
    return values[start:] if values else []


def _power_grid(lat: float, lon: float, today: date, attempts: int = 5) -> dict:
    """NASA POWER answers 429 under load: wait and ask again, longer each time."""
    for attempt in range(attempts):
        try:
            return weather._fetch_power(lat, lon, FIRST_DAY, today, None)[0]
        except GeodataError:
            if attempt == attempts - 1:
                raise
            time.sleep(15 * (attempt + 1))
    raise AssertionError("unreachable")


def snapshot(commune: dict, today: date) -> dict:
    """The app's series for the centroid (`ok` or `fallback`) and the NASA POWER grid alone."""
    lat, lon = commune["lat"], commune["lon"]
    result = weather.fetch_weather(lat, lon, today, today=today)
    w = result.data
    first = w.dates.index(FIRST_DAY.isoformat())
    out = {
        "teryt": commune["teryt"], "lat": lat, "lon": lon, "fetched": today.isoformat(),
        "status": result.status, "provider": w.provider, "grid_lat": w.latitude,
        "precipitation_sources": w.precipitation_sources, "et0_sources": w.et0_sources,
        "start": w.dates[first], "n": len(w.dates) - first,
        "precipitation_mm": w.precipitation_mm[first:], "et0_mm": w.et0_mm[first:],
        "tmean_c": _tail(w.tmean_c, first), "sunshine_h": _tail(w.sunshine_h, first),
    }  # fmt: skip
    grid = _power_grid(round(lat, 2), round(lon, 2), today)
    by_day = dict(zip(grid["dates"], zip(grid["precipitation_mm"], grid["et0_mm"], strict=True), strict=True))
    days = w.dates[first:]
    out["power"] = {
        "precipitation_mm": [by_day.get(d, (None, None))[0] for d in days],
        "et0_mm": [by_day.get(d, (None, None))[1] for d in days],
        "grid_lat": grid["latitude"],
    }
    return out


def write_whole(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, path)


def fetch_one(commune: dict, today: date, refresh: bool) -> str:
    path = OUT_DIR / f"{commune['teryt']}.json"
    if path.is_file() and not refresh:
        return "skipped"
    try:
        write_whole(path, snapshot(commune, today))
    except (GeodataError, ValueError) as exc:
        return f"FAILED {commune['teryt']} {commune['nazwa']}: {exc}"[:200]
    return "saved"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--refresh", action="store_true", help="download again although a file exists")
    ap.add_argument("--limit", type=int, default=0, help="only the first N communes")
    args = ap.parse_args(argv)
    todo = communes()[: args.limit or None]
    today = date.today()
    counts = {"saved": 0, "skipped": 0, "failed": 0}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i, msg in enumerate(pool.map(lambda c: fetch_one(c, today, args.refresh), todo), 1):
            counts["failed" if msg.startswith("FAILED") else msg] += 1
            if msg.startswith("FAILED"):
                print(msg, flush=True)
            if i % 20 == 0 or i == len(todo):
                print(f"{i}/{len(todo)} {counts}", flush=True)
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
