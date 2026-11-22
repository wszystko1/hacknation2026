"""Freeze the offline copy of the parcel picker: uv run python scripts/freeze_map.py

Writes into demo/data/map:
  tiles/{layer}/{z}/{x}/{y}.jpg  every tile of the zoom path (the middle of Poland at z=9 down to z=17 around both demo parcels,
                                 1366x768 window), the GUGiK orthophoto (WMS);
  parcels.json                   outlines of the demo parcels (from their frozen data copies) and of the parcels
                                 the report photo shows around them (ULDK GetParcelByXY on a grid of points).

`--check` writes nothing: it lists the tiles of the zoom path that are missing and exits with 1 if any is.
`--tiles` / `--parcels` freeze only that part. The copy has to stay under 10 MB.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.geodata import config as geo_config  # noqa: E402
from app.geodata.errors import GeodataError, ParcelNotFound  # noqa: E402
from app.geodata.parcel import RESULT_FIELDS, parse_uldk  # noqa: E402
from app.picker import frozen, tiles  # noqa: E402
from app.picker.zoompath import DEMO_CENTRES, path_tiles  # noqa: E402

MAX_BYTES = 10 * 1024 * 1024
GRID_STEP_M = 35.0
ULDK_MAX_BYTES = 2_000_000
JPEG_QUALITY = 60


def missing_tiles() -> list[tuple[str, int, int, int]]:
    return [t for t in path_tiles() if not tiles.frozen_path(*t).is_file()]


def tree_size(root: Path) -> int:
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file())


def check() -> int:
    missing = missing_tiles()
    for layer, z, x, y in missing:
        print(f"brak kafla {layer}/{z}/{x}/{y}")
    if not (frozen.MAP_DIR / frozen.PARCELS_FILE).is_file():
        print(f"brak pliku {frozen.PARCELS_FILE}")
        return 1
    size = tree_size(frozen.MAP_DIR)
    print(
        f"kafli w ścieżce: {len(path_tiles())}, brakuje: {len(missing)}, rozmiar kopii: {size / 1e6:.1f} MB"
    )
    return 1 if missing or size > MAX_BYTES else 0


def reencode(jpeg: bytes, quality: int) -> bytes:
    """Same pixels, smaller file: the base map is flat colours and lines, the photo tolerates quality 60."""
    import warnings

    import rasterio

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with rasterio.MemoryFile(jpeg) as src_mem, src_mem.open() as src:
            data = src.read()
            with rasterio.MemoryFile() as out_mem:
                with out_mem.open(
                    driver="JPEG", width=src.width, height=src.height, count=src.count, dtype="uint8",
                    QUALITY=quality,
                ) as dst:  # fmt: skip
                    dst.write(data)
                return out_mem.read()


def freeze_one(tile: tuple[str, int, int, int]) -> str | None:
    """None when frozen, else the reason."""
    layer, z, x, y = tile
    image = None
    for attempt in range(3):
        image = tiles.fetch_from_wms(layer, z, x, y)
        if image:
            break
        time.sleep(1.0 * (attempt + 1))
    if image is None:
        return f"{layer}/{z}/{x}/{y}: WMS nie odpowiada"
    target = tiles.frozen_path(*tile)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(reencode(image, JPEG_QUALITY))
    return None


def freeze_tiles(workers: int = 6) -> int:
    todo = missing_tiles()
    print(f"kafle: {len(todo)} do pobrania z {len(path_tiles())}")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        failures = [r for r in pool.map(freeze_one, todo) if r]
    for line in failures:
        print(line)
    return 1 if failures else 0


# ---- parcels -------------------------------------------------------------------------------------------------


def _record(parcel) -> dict:  # noqa: ANN001 - app.geodata.models.Parcel
    return {
        "dzialka": parcel.id,
        "numer": parcel.number,
        "obreb": parcel.precinct,
        "gmina": parcel.commune,
        "pow_ha": round(parcel.area_ha, 2),
        "rings_2180": parcel.rings_2180,
        "rings_4326": parcel.rings_4326,
    }


def demo_parcels() -> tuple[list[dict], list[tuple[str, list[float]]]]:
    """Records of the demo parcels and (id, photo bbox in EPSG:2180) from their frozen data copies."""
    records, frames = [], []
    for path in sorted(geo_config.demo_dir().glob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            data = doc["parcel"]["data"]
            ortho = doc["ortho"]["data"]
        except (KeyError, TypeError, ValueError):
            continue
        if not data or not ortho or data["id"] not in DEMO_CENTRES:
            continue
        if any(r["dzialka"] == data["id"] for r in records):
            continue
        from app.geodata.models import Parcel

        parcel = Parcel(**data)
        records.append(_record(parcel))
        frames.append((parcel.id, ortho["bbox_2180"]))
    return records, frames


def uldk_at(client: httpx.Client, x: float, y: float):  # noqa: ANN201
    """The parcel at EPSG:2180 point (x, y). Refuses redirects and oversized answers: ULDK sometimes sends a stub."""
    params = {
        "request": "GetParcelByXY",
        "xy": f"{x:.2f},{y:.2f},2180",
        "result": RESULT_FIELDS,
        "srid": "2180",
    }
    with client.stream("GET", geo_config.ULDK_URL, params=params) as resp:
        if resp.is_redirect:
            raise GeodataError(
                f"ULDK przekierowuje na {resp.headers.get('location')}: usługa odmawia odpowiedzi"
            )
        body = b""
        for chunk in resp.iter_bytes():
            body += chunk
            if len(body) > ULDK_MAX_BYTES:
                raise GeodataError("ULDK odpowiada zbyt dużym ładunkiem, to nie jest odpowiedź o działce")
    return parse_uldk(body.decode("utf-8", errors="replace"))


def freeze_parcels() -> int:
    records, frames = demo_parcels()
    if len(records) != len(DEMO_CENTRES):
        print("brak kopii danych obu działek demo w demo/data/geodata")
        return 1
    known = {r["dzialka"]: r for r in records}
    shapes = [
        frozen.FrozenParcel(
            r["dzialka"], r["numer"], r["obreb"], r["gmina"], r["pow_ha"], r["rings_2180"], r["rings_4326"],
            (
                min(p[0] for ring in r["rings_2180"] for p in ring),
                min(p[1] for ring in r["rings_2180"] for p in ring),
                max(p[0] for ring in r["rings_2180"] for p in ring),
                max(p[1] for ring in r["rings_2180"] for p in ring),
            ),
        )
        for r in records
    ]  # fmt: skip
    client = httpx.Client(headers={"User-Agent": geo_config.USER_AGENT}, timeout=10.0, follow_redirects=False)
    asked = 0
    failed = False
    try:
        for _, (xmin, ymin, xmax, ymax) in frames:
            y = ymin + GRID_STEP_M / 2
            while y < ymax:
                x = xmin + GRID_STEP_M / 2
                while x < xmax:
                    if not any(s.contains(x, y) for s in shapes):
                        asked += 1
                        try:
                            parcel = uldk_at(client, x, y)
                        except ParcelNotFound:
                            parcel = None
                        if parcel is not None and parcel.id not in known:
                            rec = _record(parcel)
                            known[parcel.id] = rec
                            shapes.append(
                                frozen.FrozenParcel(
                                    rec["dzialka"], rec["numer"], rec["obreb"], rec["gmina"], rec["pow_ha"],
                                    rec["rings_2180"], rec["rings_4326"], tuple(parcel.bbox_2180),
                                )
                            )  # fmt: skip
                    x += GRID_STEP_M
                y += GRID_STEP_M
    except (GeodataError, httpx.HTTPError) as exc:
        print(f"działki sąsiadów: {exc}; zapisuję same działki demo")
        failed = True
    finally:
        client.close()
    out = {
        "source": "ULDK GUGiK (GetParcelByXY), obrysy EGiB w EPSG:2180; działki demo z kopii danych działek",
        "retrieved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "parcels": sorted(known.values(), key=lambda r: r["dzialka"]),
    }
    path = frozen.MAP_DIR / frozen.PARCELS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"działki: {len(known)} (zapytań do ULDK: {asked}), plik {path.stat().st_size / 1e3:.0f} kB")
    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="list missing tiles, exit 1 if any is missing")
    ap.add_argument("--tiles", action="store_true", help="freeze only the tiles")
    ap.add_argument("--parcels", action="store_true", help="freeze only the parcel outlines")
    args = ap.parse_args()
    if args.check:
        return check()
    both = not (args.tiles or args.parcels)
    code = 0
    if args.tiles or both:
        code |= freeze_tiles()
    if args.parcels or both:
        code |= freeze_parcels()
    code |= check()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
