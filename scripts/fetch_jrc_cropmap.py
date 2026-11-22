"""Download the inputs of the rotation-group check: `uv run python scripts/fetch_jrc_cropmap.py`.

For every parcel of demo/data/eval/parcels50.csv (outline from ULDK) it reads, for 2018 and 2022,
  - the class histogram of the JRC EUCROPMAP pixels inside the outline (windowed read of the remote GeoTIFF,
    the whole 2018 file is 6.7 GB so it is not downloaded), written to data/raw/jrc_cropmap/classes.csv;
  - the Sentinel-2 readings of that season (app.geodata.satellite.fetch_season), written to
    data/raw/jrc_cropmap/seasons/<parcel>.json.
`make eval ONLY=rotation` reads both. Needs the network; parcels already fetched are skipped, so a rerun
resumes. JRC EUCROPMAP: CC BY 4.0, (c) European Union.
"""

from __future__ import annotations

import csv
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.geodata import normalize_parcel_id  # noqa: E402
from app.geodata.crop_hint import GDAL_ENV  # noqa: E402
from app.geodata.models import Parcel  # noqa: E402
from app.geodata.parcel import fetch_parcel, fetch_parcel_by_lonlat, to_wgs84  # noqa: E402
from app.geodata.satellite import fetch_season  # noqa: E402

URLS = {
    2018: "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/EUCROPMAP/2018/EUCROPMAP_2018.tif",
    2022: "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/EUCROPMAP/2022/EU_CropMap_22_v1_stratum_EU27-HR.tif",
}
SAMPLE = ROOT / "demo" / "data" / "eval" / "parcels50.csv"
OUT = ROOT / "data" / "raw" / "jrc_cropmap"
CLASSES = OUT / "classes.csv"
SEASONS = OUT / "seasons"


def pixel_counts(parcel, url: str) -> dict[int, int]:
    """Pixel count per class code inside the parcel outline."""
    import numpy as np
    import rasterio
    from pyproj import Transformer
    from rasterio.features import geometry_mask
    from rasterio.windows import from_bounds
    from rasterio.windows import transform as window_transform

    with rasterio.Env(**GDAL_ENV), rasterio.open(url) as ds:
        tr = Transformer.from_crs(2180, ds.crs, always_xy=True)
        ring = [tr.transform(x, y) for x, y in parcel.rings_2180[0]]
        xs, ys = [p[0] for p in ring], [p[1] for p in ring]
        window = from_bounds(min(xs), min(ys), max(xs), max(ys), ds.transform).round_offsets().round_lengths()
        data = ds.read(1, window=window)
        transform = window_transform(window, ds.transform)
    geometry = {"type": "Polygon", "coordinates": [ring]}
    mask = geometry_mask([geometry], out_shape=data.shape, transform=transform, invert=True)
    if mask.sum() < 4:
        mask = geometry_mask(
            [geometry], out_shape=data.shape, transform=transform, invert=True, all_touched=True
        )
    values = data[mask]
    values = values[values > 0]
    codes, counts = np.unique(values, return_counts=True)
    return {int(c): int(n) for c, n in zip(codes, counts, strict=True)}


SQUARE_HALF_SIDE_M = 50.0  # the stand-in outline is 100 x 100 m = 1 ha


def square_around(lon: float, lat: float) -> Parcel:
    """A 1 ha square around the point, used when the cadastre service gives no outline.

    The satellite curve and the map class are then read for the same square, which is what the
    comparison needs; the rows of classes.csv for such parcels start with "punkt_".
    """
    from pyproj import Transformer

    x, y = Transformer.from_crs(4326, 2180, always_xy=True).transform(lon, lat)
    h = SQUARE_HALF_SIDE_M
    ring = [[x - h, y - h], [x + h, y - h], [x + h, y + h], [x - h, y + h], [x - h, y - h]]
    ring_wgs = [to_wgs84(a, b) for a, b in ring]
    return Parcel(
        id=f"punkt_{lon:.5f}_{lat:.5f}", voivodeship="", county="", commune="", precinct="", number="",
        area_ha=(2 * h) ** 2 / 10_000, rings_2180=[ring], rings_4326=[ring_wgs], centroid_2180=[x, y],
        centroid_4326=[lon, lat], bbox_2180=[x - h, y - h, x + h, y + h],
        bbox_4326=[ring_wgs[0][0], ring_wgs[0][1], ring_wgs[2][0], ring_wgs[2][1]],
    )  # fmt: skip


def load_parcel(row: dict[str, str]) -> Parcel | None:
    """The parcel outline from ULDK; for a row with coordinates a square when ULDK does not answer."""
    try:
        if row["dzialka"]:
            result = fetch_parcel(row["dzialka"])
        else:
            result = fetch_parcel_by_lonlat(float(row["lon"]), float(row["lat"]))
        if result.usable:
            return result.data
    except Exception as exc:  # noqa: BLE001 - ULDK outages come in many shapes
        print("ULDK:", exc)
    if row["lon"] and row["lat"]:
        return square_around(float(row["lon"]), float(row["lat"]))
    return None


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    SEASONS.mkdir(exist_ok=True)
    known = set()
    if CLASSES.is_file():
        with CLASSES.open(encoding="utf-8", newline="") as f:
            known = {r["parcel"] for r in csv.DictReader(f)}
    new_file = not CLASSES.is_file()
    with (
        SAMPLE.open(encoding="utf-8", newline="") as f,
        CLASSES.open("a", encoding="utf-8", newline="") as out,
    ):
        writer = csv.writer(out)
        if new_file:
            writer.writerow(["parcel", "year", "code", "pixels"])
        for row in csv.DictReader(f):
            try:
                parcel = load_parcel(row)
                if parcel is None:
                    print("skip: no outline", row["dzialka"] or (row["lon"], row["lat"]))
                    continue
                key = (
                    parcel.id
                    if parcel.id.startswith("punkt_")
                    else normalize_parcel_id(parcel.id).replace("/", "_")
                )
                if key in known:
                    continue
                counts = {y: pixel_counts(parcel, u) for y, u in URLS.items()}
                seasons = {y: [asdict(r) for r in fetch_season(parcel, y)] for y in URLS}
            except Exception as exc:  # noqa: BLE001 - one parcel must not stop the run
                print("skip:", row["dzialka"] or (row["lon"], row["lat"]), exc)
                continue
            (SEASONS / f"{key}.json").write_text(json.dumps(seasons), encoding="utf-8")
            for year, by_code in counts.items():
                for code, n in by_code.items():
                    writer.writerow([key, year, code, n])
            out.flush()
            print("ok:", key, {y: sum(c.values()) for y, c in counts.items()}, "pixels")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
