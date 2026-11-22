"""Download BDOT10k ponds and water bodies within about 1 km of the parcels of demo/data/eval/ditch_parcels.csv.

`python scripts/fetch_ponds.py` reads the parcel list written by scripts/fetch_retention_sample.py, asks the BDOT10k map
service for the layers of water bodies (WPow, ZbTA) in a 1 km belt around each parcel and writes the outlines of one
parcel to data/raw/ponds/<id>.json. A second run skips what is already there. Needs the network; data/raw is not
committed. The height grid of each parcel reaches about 300 m beyond it, so scripts/eval_ponds.py scores the ponds
that fall inside that grid.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "data" / "raw" / "ponds"
SEARCH_M = 1000.0


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def store_path(parcel_id: str, store: Path = STORE) -> Path:
    return store / _load_script("fetch_retention_sample").store_path(parcel_id).name


def load_ponds(parcel_id: str, store: Path = STORE) -> list[list[list[list[float]]]] | None:
    """Pond outlines of a parcel ([ring][vertex][x, y] in EPSG:2180, first ring the outer one); None when not downloaded."""
    path = store_path(parcel_id, store)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))["ponds"]


def fetch_all() -> int:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from app.geodata import fetch_water

    sample = _load_script("fetch_retention_sample")
    if not sample.CSV_PATH.is_file():
        print(f"{sample.CSV_PATH} is missing: run scripts/fetch_retention_sample.py first")
        return 0
    STORE.mkdir(parents=True, exist_ok=True)
    kept = 0
    for row in sample.read_rows():
        pid = row["dzialka"]
        if store_path(pid).is_file():
            kept += 1
            continue
        loaded = sample.load_parcel(pid)
        if loaded is None:
            print(f"  {pid}: no parcel file, skipped")
            continue
        try:
            found = fetch_water(loaded[0], search_m=SEARCH_M)
        except Exception as exc:  # noqa: BLE001 - one parcel that fails does not stop the others
            print(f"  {pid}: {type(exc).__name__}: {exc}")
            continue
        if not found.usable:
            print(f"  {pid}: water not read ({found.error})")
            continue
        ponds = [f.rings_2180 for f in found.data.features if f.kind == "water_body" and f.rings_2180]
        store_path(pid).write_text(
            json.dumps({"parcel": pid, "ponds": ponds}, separators=(",", ":")), "utf-8"
        )
        kept += 1
        print(f"  {pid}: {len(ponds)} water bodies")
    print(f"{STORE}: {kept} parcels")
    return kept


if __name__ == "__main__":
    fetch_all()
