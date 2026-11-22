"""Freeze parcel outlines into demo/data/map/parcels.json: uv run python scripts/freeze_parcels.py

Reads the identifiers and points of demo/data/eval/parcels50.csv and the two demo parcels, asks ULDK and then the
EGiB WFS for each outline and merges them into the map copy (the same file the parcel picker reads). Coordinates
are rounded to 0.1 m. Every parcel carries `pobrano: true`; the ones that could not be fetched are listed in
`niepobrane`, so the file says plainly which rows are real downloads. Run it on a machine with network access;
without it the script stops with a message. The file has to stay under 1 MB.
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.geodata import config, parcel_wfs, uldk_guard  # noqa: E402
from app.geodata.errors import GeodataError  # noqa: E402
from app.geodata.models import Parcel  # noqa: E402
from app.geodata.parcel import RESULT_FIELDS, normalize_parcel_id, parse_uldk  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "demo" / "data" / "map" / "parcels.json"
CSV = ROOT / "demo" / "data" / "eval" / "parcels50.csv"
DEMO_IDS = ["040303_2.0002.189/13", "100403_2.0011.144"]
MAX_BYTES = 1_000_000
Item = str | tuple[float, float]  # an identifier or (lon, lat)


def items_from_csv(path: Path = CSV) -> list[Item]:
    found: list[Item] = list(DEMO_IDS)
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("dzialka"):
                found.append(row["dzialka"].strip())
            elif row.get("lon") and row.get("lat"):
                found.append((float(row["lon"]), float(row["lat"])))
    return found


def fetch_item(item: Item) -> Parcel:
    """Outline of one item: ULDK first, the EGiB WFS when ULDK does not answer."""
    if isinstance(item, str):
        pid = normalize_parcel_id(item)
        params = {"request": "GetParcelById", "id": pid, "result": RESULT_FIELDS, "srid": "2180"}
    else:
        params = {
            "request": "GetParcelByXY",
            "xy": f"{item[0]},{item[1]},4326",
            "result": RESULT_FIELDS,
            "srid": "2180",
        }
    try:
        return parse_uldk(uldk_guard.fetch(params, geometry=True).text)
    except GeodataError:
        pass
    if isinstance(item, str):
        return parcel_wfs.parcel_by_id(pid)
    from pyproj import Transformer

    x, y = Transformer.from_crs(4326, 2180, always_xy=True).transform(*item)
    return parcel_wfs.parcel_at_point(x, y)


def entry(parcel: Parcel) -> dict:
    def r(rings: list, nd: int) -> list:
        return [[[round(v, nd) for v in p] for p in ring] for ring in rings]

    return {
        "dzialka": parcel.id,
        "numer": parcel.number,
        "obreb": parcel.precinct,
        "gmina": parcel.commune,
        "pow_ha": round(parcel.area_ha, 2),
        "rings_2180": r(parcel.rings_2180, 1),
        "rings_4326": r(parcel.rings_4326, 6),
        "pobrano": True,
        "zrodlo": parcel.outline_source,
    }


def freeze(items: list[Item], out: Path = OUT) -> dict:
    """Fetch every item, merge into the existing file by identifier, write it. Raises ValueError over 1 MB."""
    existing: dict = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {"parcels": []}
    by_id = {p["dzialka"]: p for p in existing.get("parcels", [])}
    missing: list[str] = []
    for item in items:
        try:
            parcel = fetch_item(item)
        except GeodataError as exc:
            missing.append(item if isinstance(item, str) else f"{item[0]},{item[1]}")
            print(f"nie pobrano {item}: {exc}", file=sys.stderr)
            continue
        by_id[parcel.id] = entry(parcel)
    data = {
        "source": "ULDK GUGiK, a gdy nie odpowiada EGiB WFS (ms:dzialki); obrysy w EPSG:2180, zaokrąglone do 0,1 m",
        "retrieved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "niepobrane": missing,
        "parcels": list(by_id.values()),
    }
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    if len(text.encode("utf-8")) >= MAX_BYTES:
        raise ValueError("parcels.json would exceed 1 MB; shorten the list")
    out.write_text(text, encoding="utf-8")
    return data


def main() -> int:
    if config.is_offline():
        print("GEODATA_OFFLINE is set: freezing outlines needs the network.", file=sys.stderr)
        return 1
    try:
        data = freeze(items_from_csv())
    except (ValueError, OSError) as exc:
        print(f"Nie zapisano {OUT}: {exc}", file=sys.stderr)
        return 1
    fetched = sum(1 for p in data["parcels"] if p.get("pobrano"))
    if fetched == 0:
        print("Brak sieci albo usługi GUGiK nie odpowiadają: nic nie pobrano.", file=sys.stderr)
        return 1
    print(f"{OUT}: {len(data['parcels'])} działek, nie pobrano {len(data['niepobrane'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
