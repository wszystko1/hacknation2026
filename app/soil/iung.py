"""Reading of the IUNG-PIB map "Kategorie podatności gleb na suszę" (layer Susza:katgl_landuse2024) for a parcel.

The layer is a raster served by a GeoServer (WMS GetFeatureInfo gives the cell value as GRAY_INDEX). We read a
grid of points inside the parcel outline and keep the count of every cell value, so the report can say
"kat. II w 8 z 9 punktów". Values 1-4 are the categories; 5 is organic soil; 11-19 and 99 are land cover the map
masks out (forest, water, built-up land). Frozen readings of the demo parcels live in demo/data/soil/.
"""

from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.geodata import cache, config, http
from app.geodata.errors import GeodataError
from app.geodata.models import now_iso
from app.models import SOIL_CATEGORIES, SoilCategory

URL = "https://sgeo.iung.pl/geoserver/ows"
LAYER = "Susza:katgl_landuse2024"
PROVIDER = "IUNG-PIB, mapa podatności gleb na suszę"
ORGANIC = 5
MAX_POINTS = 9
POINT_TIMEOUT_S = 5.0
TOTAL_BUDGET_S = 9.0
_HALF_CELL_DEG = 0.0005  # the query window around a point; the raster is read at its centre pixel


def frozen_dir() -> Path:
    return config.repo_root() / "demo" / "data" / "soil"


def stem(parcel_id: str) -> str:
    return re.sub(r"[^0-9A-Za-z]+", "_", parcel_id).strip("_")


@dataclass
class IungReading:
    parcel_id: str
    counts: dict[str, int] = field(default_factory=dict)  # cell value -> number of sampled points
    points: int = 0  # points asked, including those without an answer
    url: str = ""
    retrieved_at: str = ""
    layer: str = LAYER

    @property
    def answered(self) -> int:
        return sum(self.counts.values())


@dataclass
class IungCategory:
    category: SoilCategory | None
    other: (
        SoilCategory | None
    )  # the second most frequent category when it covers a quarter of the points or more
    in_points: int  # points with the chosen category
    of_points: int  # points with any category I-IV
    organic: bool = False  # no category I-IV, the map shows organic soil


def classify(reading: IungReading) -> IungCategory:
    """Most frequent category I-IV among the points; a tie goes to the more susceptible (lower) one."""
    per_category = {c: reading.counts.get(str(i + 1), 0) for i, c in enumerate(SOIL_CATEGORIES)}
    of_points = sum(per_category.values())
    if of_points == 0:
        return IungCategory(None, None, 0, 0, organic=reading.counts.get(str(ORGANIC), 0) > 0)
    ranked = sorted(per_category.items(), key=lambda kv: (-kv[1], SOIL_CATEGORIES.index(kv[0])))
    best, count = ranked[0]
    second, second_count = ranked[1]
    other = second if second_count and second_count / of_points >= 0.25 else None
    return IungCategory(best, other, count, of_points)


def _inside(lon: float, lat: float, ring: list[list[float]]) -> bool:
    inside = False
    j = len(ring) - 1
    for i, (xi, yi) in enumerate(ring):
        xj, yj = ring[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def sample_points(rings_4326: list[list[list[float]]], limit: int = MAX_POINTS) -> list[tuple[float, float]]:
    """Points of a 5 x 5 grid over the bounding box that fall in the outline (not in its holes), evenly thinned."""
    outline = rings_4326[0]
    holes = rings_4326[1:]
    lons = [p[0] for p in outline]
    lats = [p[1] for p in outline]
    found: list[tuple[float, float]] = []
    for row in range(5):
        for col in range(5):
            lon = min(lons) + (max(lons) - min(lons)) * (col + 0.5) / 5
            lat = min(lats) + (max(lats) - min(lats)) * (row + 0.5) / 5
            if _inside(lon, lat, outline) and not any(_inside(lon, lat, h) for h in holes):
                found.append((lon, lat))
    if len(found) > limit:
        found = [found[int(i * len(found) / limit)] for i in range(limit)]
    if not found:  # a sliver: the mean of the outline vertices
        found = [(sum(lons) / len(lons), sum(lats) / len(lats))]
    return found


def _read_point(lon: float, lat: float, deadline: float) -> str | None:
    d = _HALF_CELL_DEG
    params = {
        "service": "WMS", "version": "1.3.0", "request": "GetFeatureInfo",
        "layers": LAYER, "query_layers": LAYER, "crs": "EPSG:4326",
        "bbox": f"{lat - d},{lon - d},{lat + d},{lon + d}",  # WMS 1.3.0 with EPSG:4326: latitude first
        "width": 101, "height": 101, "i": 50, "j": 50,
        "info_format": "application/json", "feature_count": 1,
    }  # fmt: skip
    try:
        resp = http.get(URL, params=params, timeout=POINT_TIMEOUT_S, retries=0, deadline=deadline)
        if resp.status_code != 200:
            return None
        features = resp.json().get("features") or []
        value = (features[0].get("properties") or {}).get("GRAY_INDEX") if features else None
    except (GeodataError, ValueError):
        return None
    return None if value is None else str(int(float(value)))


def read_live(parcel_id: str, rings_4326: list[list[list[float]]]) -> IungReading | None:
    """Ask the service. None when fewer than half of the points answered (nothing worth keeping)."""
    points = sample_points(rings_4326)
    deadline = time.monotonic() + TOTAL_BUDGET_S
    with ThreadPoolExecutor(max_workers=6) as pool:
        values = list(pool.map(lambda p: _read_point(p[0], p[1], deadline), points))
    counts: dict[str, int] = {}
    for v in values:
        if v is not None:
            counts[v] = counts.get(v, 0) + 1
    if sum(counts.values()) * 2 < len(points):
        return None
    return IungReading(
        parcel_id=parcel_id, counts=counts, points=len(points), url=f"{URL}?layers={LAYER}",
        retrieved_at=now_iso(),
    )  # fmt: skip


def _from_dict(raw: dict) -> IungReading:
    return IungReading(**{k: raw[k] for k in IungReading.__dataclass_fields__ if k in raw})


def load_frozen(parcel_id: str, directory: Path | None = None) -> IungReading | None:
    path = (directory or frozen_dir()) / f"{stem(parcel_id)}.json"
    if not path.is_file():
        return None
    return _from_dict(json.loads(path.read_text(encoding="utf-8")))


def save_frozen(reading: IungReading, directory: Path | None = None) -> Path:
    directory = directory or frozen_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{stem(reading.parcel_id)}.json"
    path.write_text(json.dumps(asdict(reading), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path


def read_for_parcel(parcel_id: str, rings_4326: list[list[list[float]]]) -> tuple[IungReading | None, bool]:
    """(reading or None, from a frozen copy). Order: frozen demo copy, disk cache, the service (not offline)."""
    frozen = load_frozen(parcel_id)
    if frozen is not None:
        return frozen, True
    hit = cache.get_json("iung", parcel_id)
    if hit is not None:
        return _from_dict(hit), False
    if config.is_offline():
        return None, False
    reading = read_live(parcel_id, rings_4326)
    if reading is not None:
        cache.put_json("iung", parcel_id, asdict(reading))
    return reading, False
