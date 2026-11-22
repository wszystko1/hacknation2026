"""Robustness: how long a report takes for 20 parcels from different voivodeships, and how many finish in 30 s.

`make eval ONLY=robustness` picks 20 rows of demo/data/eval/parcels50.csv (one per voivodeship, then 2 dated
today and 2 outside the monitoring season), builds each report with an empty download cache, one after
another, and writes robustness.report_ok_under_30s_share, p50_s, p95_s, n_parcels, n_voivodeships and
n_no_weather. The outline of the parcel comes the way the app gets it (local copy, ULDK, EGiB WFS), so the
time is what a user sees. A report is ok when it is built within 30 s with a verdict; "no weather" is built,
but not ok. The time is measured from our network, not from the room of the demo.
Needs the network; without it `run()` returns nothing and metrics.json keeps its values.
"""

from __future__ import annotations

import os
import shutil
import sys
import time
from collections.abc import Callable
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import eval_parcels as common  # noqa: E402

WORK = ROOT / "data" / "raw" / "eval_robustness"
LIMIT_S = 30.0
N_PARCELS = 20
TODAY = common.TODAY


def _kind(row: dict[str, str]) -> str:
    if row["data"] == TODAY:
        return "dzis"
    month_day = (int(row["data"][5:7]), int(row["data"][8:10]))
    return "sezon" if (3, 21) <= month_day <= (9, 30) else "poza"


def select(rows: list[dict[str, str]], n: int = N_PARCELS) -> list[dict[str, str]]:
    """One row per voivodeship (the first one with a parcel id, else the first), then the remaining places
    go to rows dated today and outside the season, alternating. Deterministic: depends on the file only."""
    by_voivodeship: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_voivodeship.setdefault(row["wojewodztwo"], []).append(row)
    chosen = []
    for name in sorted(by_voivodeship):
        group = by_voivodeship[name]
        chosen.append(next((r for r in group if r["dzialka"]), group[0]))
    chosen = chosen[:n]
    rest = {k: [r for r in rows if r not in chosen and _kind(r) == k] for k in ("dzis", "poza")}
    while len(chosen) < n and (rest["dzis"] or rest["poza"]):
        for kind in ("dzis", "poza"):
            if rest[kind] and len(chosen) < n:
                chosen.append(rest[kind].pop(0))
    return chosen


def measure(
    rows: list[dict[str, str]],
    today: date | None = None,
    clock: Callable[[], float] = time.perf_counter,
    build: Callable | None = None,
) -> dict[str, float | int]:
    """Build every row's report with an empty cache and time it. Returns {} when no report was built."""
    from app.models import CropGroup, ReportRequest

    if build is None:
        from app.report import build_report as build

    today = today or date.today()
    shutil.rmtree(WORK / "cache", ignore_errors=True)
    previous = os.environ.get("GEODATA_CACHE_DIR")
    times, ok, no_weather, built, codes = [], 0, 0, 0, set()
    try:
        for i, row in enumerate(rows, start=1):
            pid = row["dzialka"] or common.parcel_of_point(float(row["lon"]), float(row["lat"]))
            if not pid:
                print(f"  {i:2d}  {row['wojewodztwo']}: no parcel under the point, counted as failed")
                times.append(LIMIT_S)
                continue
            codes.add(pid[:2])
            day = today if row["data"] == TODAY else date.fromisoformat(row["data"])
            req = ReportRequest(parcel_id=pid, day=day, crop=CropGroup(row["uprawa"]))
            os.environ["GEODATA_CACHE_DIR"] = str(WORK / "cache")  # cold: the parcel is downloaded again too
            started = clock()
            try:
                state = build(req).verdict.state
                built += 1
            except Exception as exc:  # noqa: BLE001 - a failed report is a result, not a crash of the evaluation
                state = f"failed: {type(exc).__name__}"
            took = clock() - started
            times.append(took)
            no_weather += state == "no_data"
            ok += took < LIMIT_S and not state.startswith("failed") and state != "no_data"
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
        "robustness.p50_s": round(common.percentile(times, 0.5), 1),
        "robustness.p95_s": round(common.percentile(times, 0.95), 1),
    }


def run() -> dict[str, float | int]:
    if not common.CSV_PATH.is_file():
        return {}
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    return measure(select(common.read_rows()))


if __name__ == "__main__":
    print(run())
