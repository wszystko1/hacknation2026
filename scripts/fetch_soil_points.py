"""Download the points for the soil-rule check: IUNG category (map) and SoilGrids texture at the same place.

Draws random points over farmland boxes of all 16 voivodeships (fixed seed), reads the cell of the IUNG-PIB map
"Kategorie podatności gleb na suszę" (WMS GetFeatureInfo) and the SoilGrids 0-30 cm sand, silt and clay, and
writes data/raw/soil_points/points.csv. A point is kept only when the map gives category I-IV (the map masks out
forest, water, built-up land and marks organic soil as 5) and SoilGrids gives all three fractions.
`make eval ONLY=soil` reads the CSV. Needs the network; rerun to refresh. Usage: python scripts/fetch_soil_points.py
"""

from __future__ import annotations

import csv
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.geodata.soil import fetch_soil  # noqa: E402
from app.soil import iung  # noqa: E402

OUT = ROOT / "data" / "raw" / "soil_points" / "points.csv"
COLUMNS = ["voivodeship", "lon", "lat", "iung_category", "sand_pct", "silt_pct", "clay_pct"]
SEED = 20261121
PER_VOIVODESHIP = 6  # kept points per voivodeship: 16 x 6 = 96, the aim is about 100
MAX_DRAWS = 40  # random points tried per voivodeship before giving up on it
WORKERS = 4
IUNG_BUDGET_S = 20.0
SOILGRIDS_TIMEOUT_S = 25.0

# Farmland areas, one box (lon_min, lon_max, lat_min, lat_max) per voivodeship.
BOXES = {
    "dolnośląskie": (16.55, 16.95, 51.10, 51.30), "kujawsko-pomorskie": (18.40, 18.90, 52.55, 52.80),
    "lubelskie": (23.00, 23.50, 50.60, 50.90), "lubuskie": (15.80, 16.20, 52.10, 52.30),
    "łódzkie": (19.80, 20.20, 52.00, 52.20), "małopolskie": (20.00, 20.40, 50.30, 50.50),
    "mazowieckie": (20.20, 20.80, 52.70, 52.95), "opolskie": (17.60, 18.00, 50.05, 50.25),
    "podkarpackie": (22.30, 22.70, 49.95, 50.10), "podlaskie": (22.30, 22.80, 52.80, 53.10),
    "pomorskie": (19.00, 19.30, 54.00, 54.10), "śląskie": (18.20, 18.50, 50.00, 50.20),
    "świętokrzyskie": (21.30, 21.70, 50.55, 50.75), "warmińsko-mazurskie": (20.60, 21.00, 54.20, 54.40),
    "wielkopolskie": (17.30, 17.70, 52.20, 52.40), "zachodniopomorskie": (14.70, 15.10, 53.10, 53.30),
}  # fmt: skip


def read_point(voivodeship: str, lon: float, lat: float) -> dict[str, str] | None:
    """One row, or None when the map or SoilGrids gives nothing usable for the point."""
    value = iung._read_point(lon, lat, time.monotonic() + IUNG_BUDGET_S)
    if value not in {"1", "2", "3", "4"}:
        return None
    soil = fetch_soil(lat, lon, timeout=SOILGRIDS_TIMEOUT_S)
    if not soil.usable or soil.data is None or not soil.data.available:
        return None
    return {
        "voivodeship": voivodeship, "lon": f"{lon:.5f}", "lat": f"{lat:.5f}", "iung_category": value,
        "sand_pct": str(soil.data.sand_pct), "silt_pct": str(soil.data.silt_pct),
        "clay_pct": str(soil.data.clay_pct),
    }  # fmt: skip


def collect(voivodeship: str, rng: random.Random) -> list[dict[str, str]]:
    lon_min, lon_max, lat_min, lat_max = BOXES[voivodeship]
    rows: list[dict[str, str]] = []
    for _ in range(MAX_DRAWS):
        if len(rows) >= PER_VOIVODESHIP:
            break
        row = read_point(voivodeship, rng.uniform(lon_min, lon_max), rng.uniform(lat_min, lat_max))
        if row is not None:
            rows.append(row)
    return rows


def main() -> int:
    seeds = {v: random.Random(f"{SEED}-{v}") for v in BOXES}  # one stream per voivodeship: order-independent
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        parts = list(pool.map(lambda v: collect(v, seeds[v]), BOXES))
    rows = [r for part in parts for r in part]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} points from {sum(1 for p in parts if p)} voivodeships -> {OUT.relative_to(ROOT)}")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
