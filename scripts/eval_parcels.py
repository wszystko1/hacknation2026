"""The sample of 50 parcels (demo/data/eval/parcels50.csv) and the helpers the timing run shares.

The timing run itself is scripts/eval_robustness.py; this file draws the sample and reads it.

Rows without a parcel id hold a random point; the id is found with ULDK GetParcelByXY. `python
scripts/eval_parcels.py sample` draws the points again (fixed seed), asks ULDK for the parcel under each
and writes the CSV with the ids, so that the next run does not depend on the point lookup.
Needs the network.
"""

from __future__ import annotations

import csv
import random
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "demo" / "data" / "eval" / "parcels50.csv"
COLUMNS = ["dzialka", "wojewodztwo", "lon", "lat", "data", "uprawa"]
SEED = 20261121
TODAY = "dzis"  # the date column holds this word for "the day the evaluation runs"

VOIVODESHIPS = {
    "02": "dolnośląskie", "04": "kujawsko-pomorskie", "06": "lubelskie", "08": "lubuskie", "10": "łódzkie",
    "12": "małopolskie", "14": "mazowieckie", "16": "opolskie", "18": "podkarpackie", "20": "podlaskie",
    "22": "pomorskie", "24": "śląskie", "26": "świętokrzyskie", "28": "warmińsko-mazurskie",
    "30": "wielkopolskie", "32": "zachodniopomorskie",
}  # fmt: skip

# Farmland areas, one box (lon_min, lon_max, lat_min, lat_max) per voivodeship, for the random points.
BOXES = {
    "02": (16.55, 16.95, 51.10, 51.30), "04": (18.40, 18.90, 52.55, 52.80), "06": (23.00, 23.50, 50.60, 50.90),
    "08": (15.80, 16.20, 52.10, 52.30), "10": (19.80, 20.20, 52.00, 52.20), "12": (20.00, 20.40, 50.30, 50.50),
    "14": (20.20, 20.80, 52.70, 52.95), "16": (17.60, 18.00, 50.05, 50.25), "18": (22.30, 22.70, 49.95, 50.10),
    "20": (22.30, 22.80, 52.80, 53.10), "22": (19.00, 19.30, 54.00, 54.10), "24": (18.20, 18.50, 50.00, 50.20),
    "26": (21.30, 21.70, 50.55, 50.75), "28": (20.60, 21.00, 54.20, 54.40), "30": (17.30, 17.70, 52.20, 52.40),
    "32": (14.70, 15.10, 53.10, 53.30),
}  # fmt: skip


def read_rows(path: Path | None = None) -> list[dict[str, str]]:
    path = path or CSV_PATH
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_rows(rows: list[dict[str, str]], path: Path | None = None) -> None:
    path = path or CSV_PATH
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def draw_dates(rng: random.Random, n: int, today: date) -> list[str]:
    """Three kinds in the proportion 30 : 10 : 10 per 50: in the season of a past year, outside the monitoring
    period (1.X-20.III), and today. Every date lies in the last 10 years."""
    kinds = ["sezon"] * (n * 3 // 5) + ["poza"] * (n // 5)
    kinds += [TODAY] * (n - len(kinds))
    rng.shuffle(kinds)
    out = []
    for kind in kinds:
        if kind == TODAY:
            out.append(TODAY)
        elif kind == "sezon":
            year = rng.randint(2016, today.year - 1)
            start = date(year, 3, 21)
            out.append((start + timedelta(days=rng.randint(0, (date(year, 9, 30) - start).days))).isoformat())
        else:
            year = rng.randint(2016, today.year - 1)
            start = date(year, 10, 1)
            out.append(
                (start + timedelta(days=rng.randint(0, (date(year + 1, 3, 20) - start).days))).isoformat()
            )
    return out


def draw_points(rng: random.Random, per_voivodeship: tuple[int, ...]) -> list[tuple[str, float, float]]:
    points = []
    for code, count in zip(BOXES, per_voivodeship, strict=True):
        lon0, lon1, lat0, lat1 = BOXES[code]
        for _ in range(count):
            points.append((code, round(rng.uniform(lon0, lon1), 5), round(rng.uniform(lat0, lat1), 5)))
    return points


def new_rows(known: dict[str, str] | None = None, today: date | None = None) -> list[dict[str, str]]:
    """50 rows: 3 per voivodeship and 2 more in the first two; `known` maps a voivodeship code to a parcel id
    that replaces the first random point of that voivodeship."""
    from app.models import CropGroup

    today = today or date.today()
    rng = random.Random(SEED)
    counts = tuple(4 if i < 2 else 3 for i in range(16))
    points = draw_points(rng, counts)
    dates = draw_dates(rng, len(points), today)
    crops = [c.value for c in CropGroup if c is not CropGroup.INNA]
    rows, used = [], set()
    for (code, lon, lat), day in zip(points, dates, strict=True):
        row = {
            "dzialka": "", "wojewodztwo": VOIVODESHIPS[code], "lon": f"{lon:.5f}", "lat": f"{lat:.5f}",
            "data": day, "uprawa": rng.choice(crops),
        }  # fmt: skip
        if known and code in known and code not in used:
            used.add(code)
            row |= {"dzialka": known[code], "lon": "", "lat": ""}
        rows.append(row)
    return rows


# ---- the network part --------------------------------------------------------------------------------------


def parcel_of_point(lon: float, lat: float) -> str | None:
    from app.geodata import fetch_parcel_by_lonlat

    try:
        found = fetch_parcel_by_lonlat(lon, lat)
    except Exception as exc:  # noqa: BLE001 - a point without a parcel is skipped, not fatal
        print(f"  no parcel at {lon},{lat}: {exc}")
        return None
    return found.data.id if found.usable else None


def sample() -> None:
    """Write the CSV with real ids: a random point per row, redrawn until ULDK names a parcel in that
    voivodeship (the first parcel under the point)."""
    sys.path.insert(0, str(ROOT))
    rows = new_rows()
    rng = random.Random(SEED + 1)
    names = {v: k for k, v in VOIVODESHIPS.items()}
    for row in rows:
        code = names[row["wojewodztwo"]]
        lon0, lon1, lat0, lat1 = BOXES[code]
        lon, lat = float(row["lon"]), float(row["lat"])
        for _ in range(8):
            pid = parcel_of_point(lon, lat)
            if pid and pid.startswith(code):
                row |= {"dzialka": pid, "lon": f"{lon:.5f}", "lat": f"{lat:.5f}"}
                break
            lon, lat = round(rng.uniform(lon0, lon1), 5), round(rng.uniform(lat0, lat1), 5)
        else:
            print(f"  {row['wojewodztwo']}: no parcel found, the point stays")
    write_rows(rows)
    print(f"{CSV_PATH}: {sum(1 for r in rows if r['dzialka'])} of {len(rows)} rows have a parcel id")


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    pos = (len(ordered) - 1) * p
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (pos - low)


if __name__ == "__main__":
    if sys.argv[1:] == ["sample"]:
        sample()
    else:
        print("usage: python scripts/eval_parcels.py sample  (the timing run is scripts/eval_robustness.py)")
