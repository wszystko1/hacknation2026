# ruff: noqa
"""Pobranie próbki (te same 50 działek z ditch_parcels.csv) do data/raw/ponds_matched/data; the repository is not touched."""

import csv
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

P = Path(__file__).resolve().parents[2]  # product root
W = P / "data" / "raw" / "ponds_matched"  # downloaded sample and cache (not in the repository)
os.environ["GEODATA_CACHE_DIR"] = str(W / "cache")
sys.path.insert(0, str(P))
import re

from app.geodata import fetch_parcel_by_lonlat, fetch_terrain, fetch_water
from app.geodata.models import to_jsonable


def sp(pid):
    return re.sub(r"[^0-9A-Za-z]+", "_", pid).strip("_") + ".json"


rows = list(csv.DictReader(open(P / "demo/data/eval/ditch_parcels.csv", encoding="utf-8")))
T0 = time.monotonic()
LIMIT = float(sys.argv[1]) if len(sys.argv) > 1 else 480


def one(row):
    pid = row["dzialka"]
    if (W / "data/ponds" / sp(pid)).exists():
        return pid, "cached"
    if time.monotonic() - T0 > LIMIT:
        return pid, "timeout-skip"
    for attempt in range(4):
        try:
            f = fetch_parcel_by_lonlat(float(row["lon"]), float(row["lat"]))
            if not f.usable:
                raise RuntimeError(f"parcel {f.error}")
            parcel = f.data
            t = fetch_terrain(parcel, with_catchment=True)
            if not t.usable or t.data.catchment_grid is None:
                raise RuntimeError(f"terrain {t.error}")
            w = fetch_water(parcel, search_m=1000.0)
            if not w.usable:
                raise RuntimeError(f"water {w.error}")
            ponds = [x.rings_2180 for x in w.data.features if x.kind == "water_body" and x.rings_2180]
            (W / "data/retention_sample" / sp(pid)).write_text(
                json.dumps(
                    {
                        "parcel": to_jsonable(parcel),
                        "terrain": to_jsonable(t.data),
                        "water": to_jsonable(w.data),
                    },
                    separators=(",", ":"),
                ),
                "utf-8",
            )
            (W / "data/ponds" / sp(pid)).write_text(
                json.dumps({"parcel": pid, "ponds": ponds}, separators=(",", ":")), "utf-8"
            )
            return pid, f"ok ponds={len(ponds)}"
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            time.sleep(2)
    return pid, "FAIL " + err[:150]


with ThreadPoolExecutor(6) as ex:
    for pid, st in ex.map(one, rows):
        print(f"{time.monotonic() - T0:5.0f}s {pid} {st}", flush=True)
