"""Draw about 50 farmland parcels with a BDOT10k ditch within 50 m of the boundary and download their terrain.

`python scripts/fetch_retention_sample.py [target]` (default 50) picks random points in farmland boxes (the boxes of
scripts/eval_parcels.py, one voivodeship after another), asks ULDK for the parcel under each point, downloads the
BDOT10k water around it and keeps the parcel when a ditch lies within 50 m of its boundary. For the kept parcels it
downloads the height grid with the 300 m margin (`with_catchment=True`) and writes everything for one parcel to
data/raw/retention_sample/<id>.json. The list goes to demo/data/eval/ditch_parcels.csv (the only committed part;
data/raw is not). A second run continues where the first stopped. Needs the network.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "demo" / "data" / "eval" / "ditch_parcels.csv"
STORE = ROOT / "data" / "raw" / "retention_sample"
COLUMNS = ["dzialka", "wojewodztwo", "lon", "lat", "area_ha", "ditch_m"]
DITCH_MAX_M = 50.0
AREA_RANGE_HA = (0.5, 15.0)  # smaller is a garden plot; larger does not fit the margin grid at 10 m
SEED = 20261122
MAX_TRIES = 900
WORKERS = 4


def _eval_parcels():
    spec = importlib.util.spec_from_file_location("eval_parcels", ROOT / "scripts" / "eval_parcels.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def store_path(parcel_id: str) -> Path:
    return STORE / (re.sub(r"[^0-9A-Za-z]+", "_", parcel_id).strip("_") + ".json")


def read_rows(path: Path = CSV_PATH) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_rows(rows: list[dict[str, str]], path: Path = CSV_PATH) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def load_parcel(parcel_id: str, store: Path | None = None):
    """(parcel, terrain, water) saved by this script, or None when the file is missing."""
    from app.geodata.models import Parcel, Terrain, Water, from_dict

    path = store_path(parcel_id) if store is None else store / store_path(parcel_id).name
    if not path.is_file():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    return (
        from_dict(Parcel, raw["parcel"]),
        from_dict(Terrain, raw["terrain"]),
        from_dict(Water, raw["water"]),
    )


def try_point(code: str, lon: float, lat: float, names: dict[str, str]) -> dict[str, str] | None:
    """One random point: the parcel under it, kept when it has a ditch within 50 m and a margin grid."""
    from app.geodata import fetch_parcel_by_lonlat, fetch_terrain, fetch_water
    from app.geodata.models import to_jsonable

    try:
        found = fetch_parcel_by_lonlat(lon, lat)
        if not found.usable or not found.data.id.startswith(code):
            return None
        parcel = found.data
        if not AREA_RANGE_HA[0] <= parcel.area_ha <= AREA_RANGE_HA[1]:
            return None
        water = fetch_water(parcel)
        if not water.usable:
            return None
        ditches = [f.distance_m for f in water.data.features if f.kind == "ditch" and f.rings_2180]
        if not ditches or min(ditches) > DITCH_MAX_M:
            return None
        terrain = fetch_terrain(parcel, with_catchment=True)
        if not terrain.usable or terrain.data.grid is None or terrain.data.catchment_grid is None:
            return None
    except Exception as exc:  # noqa: BLE001 - a point that fails is skipped; the draw goes on
        print(f"  {lon},{lat}: {type(exc).__name__}: {exc}")
        return None
    STORE.mkdir(parents=True, exist_ok=True)
    payload = {
        "parcel": to_jsonable(parcel),
        "terrain": to_jsonable(terrain.data),
        "water": to_jsonable(water.data),
    }
    store_path(parcel.id).write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    return {
        "dzialka": parcel.id, "wojewodztwo": names[code], "lon": f"{lon:.5f}", "lat": f"{lat:.5f}",
        "area_ha": f"{parcel.area_ha:.2f}", "ditch_m": f"{min(ditches):.1f}",
    }  # fmt: skip


def sample(target: int = 50) -> list[dict[str, str]]:
    sys.path.insert(0, str(ROOT))
    ep = _eval_parcels()
    rng = random.Random(SEED)
    codes = list(ep.BOXES)
    rows = read_rows() if CSV_PATH.is_file() else []
    seen = {r["dzialka"] for r in rows}
    started = time.monotonic()
    points = []
    for i in range(MAX_TRIES):
        code = codes[i % len(codes)]
        lon0, lon1, lat0, lat1 = ep.BOXES[code]
        points.append((code, round(rng.uniform(lon0, lon1), 5), round(rng.uniform(lat0, lat1), 5)))
    done = 0
    for start in range(0, len(points), WORKERS * 4):
        if len(rows) >= target:
            break
        batch = points[start : start + WORKERS * 4]
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            results = list(pool.map(lambda p: try_point(p[0], p[1], p[2], ep.VOIVODESHIPS), batch))
        done += len(batch)
        for row in results:
            if row and row["dzialka"] not in seen and len(rows) < target:
                seen.add(row["dzialka"])
                rows.append(row)
        write_rows(rows)
        print(f"  {done} points tried, {len(rows)} parcels kept, {time.monotonic() - started:.0f} s")
    print(f"{CSV_PATH}: {len(rows)} parcels with a ditch within {DITCH_MAX_M:.0f} m")
    return rows


if __name__ == "__main__":
    sample(int(sys.argv[1]) if len(sys.argv) > 1 else 50)
