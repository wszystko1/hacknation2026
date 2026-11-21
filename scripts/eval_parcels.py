"""Robustness: how long a report takes for parcels nobody prepared, and how many finish within 30 s.

`make eval ONLY=parcels` builds the report of each row of demo/data/eval/parcels50.csv (50 parcels from 16
voivodeships; dates in the past, outside the season and today) with an empty download cache, one after another,
and writes robustness.report_ok_under_30s_share, p50_s, p95_s and n_parcels. A report counts as ok when it
is built within 30 s and has a verdict (a report that says "no weather" is built, but not ok).

Rows without a parcel id hold a random point; the id is found with ULDK GetParcelByXY. `python
scripts/eval_parcels.py sample` draws the points again (fixed seed), asks ULDK for the parcel under each
and writes the CSV with the ids, so that the next run does not depend on the point lookup.
Needs the network; without it `run()` returns nothing and metrics.json keeps its values.
"""

from __future__ import annotations

import csv
import os
import random
import shutil
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "demo" / "data" / "eval" / "parcels50.csv"
WORK = ROOT / "data" / "raw" / "eval_parcels"
COLUMNS = ["dzialka", "wojewodztwo", "lon", "lat", "data", "uprawa"]
LIMIT_S = 30.0
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


def read_rows(path: Path = CSV_PATH) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_rows(rows: list[dict[str, str]], path: Path = CSV_PATH) -> None:
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


def measure(rows: list[dict[str, str]], today: date | None = None) -> dict[str, float | int]:
    """Build every row's report with an empty cache and time it. Returns {} when no parcel could be found."""
    from app.models import CropGroup, ReportRequest
    from app.report import build_report

    today = today or date.today()
    shutil.rmtree(WORK / "cache", ignore_errors=True)
    previous = os.environ.get("GEODATA_CACHE_DIR")
    times, ok, no_weather, built, codes = [], 0, 0, 0, set()
    try:
        for i, row in enumerate(rows, start=1):
            pid = row["dzialka"] or parcel_of_point(float(row["lon"]), float(row["lat"]))
            if not pid:
                print(f"  {i:2d}  {row['wojewodztwo']}: no parcel under the point, counted as failed")
                times.append(LIMIT_S)
                continue
            codes.add(pid[:2])
            day = today if row["data"] == TODAY else date.fromisoformat(row["data"])
            req = ReportRequest(parcel_id=pid, day=day, crop=CropGroup(row["uprawa"]))
            os.environ["GEODATA_CACHE_DIR"] = str(WORK / "cache")  # cold: the parcel is downloaded again too
            started = time.perf_counter()
            try:
                report = build_report(req)
                state = report.verdict.state
                built += 1
            except Exception as exc:  # noqa: BLE001 - a failed report is a result, not a crash of the evaluation
                state = f"failed: {type(exc).__name__}"
            took = time.perf_counter() - started
            times.append(took)
            no_weather += state == "no_data"
            is_ok = took <= LIMIT_S and not state.startswith("failed") and state != "no_data"
            ok += is_ok
            print(f"  {i:2d}  {pid:28s} {row['data']:10s} {took:5.1f} s  {state}")
    finally:
        if previous is None:
            os.environ.pop("GEODATA_CACHE_DIR", None)
        else:
            os.environ["GEODATA_CACHE_DIR"] = previous
    if not built:
        return {}
    return {
        "robustness.n_parcels": len(rows),
        "robustness.n_voivodeships": len(codes),
        "robustness.n_no_weather": no_weather,
        "robustness.report_ok_under_30s_share": round(ok / len(rows), 4),
        "robustness.p50_s": round(percentile(times, 0.5), 1),
        "robustness.p95_s": round(percentile(times, 0.95), 1),
    }


def run() -> dict[str, float | int]:
    if not CSV_PATH.is_file():
        return {}
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    return measure(read_rows())


if __name__ == "__main__":
    if sys.argv[1:] == ["sample"]:
        sample()
    else:
        print(run())
