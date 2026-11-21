"""The frozen copy of parcel outlines in demo/data/map: answers a click without ULDK.

It holds the demo parcels and the parcels around them that the report photo shows. A point is matched to an
outline in EPSG:2180 (even-odd rule over all rings, so holes and multi-part parcels work).
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from pyproj import Transformer

MAP_DIR = Path(__file__).resolve().parents[2] / "demo" / "data" / "map"
PARCELS_FILE = "parcels.json"

_local = threading.local()


@dataclass(frozen=True)
class FrozenParcel:
    dzialka: str
    numer: str
    obreb: str
    gmina: str
    pow_ha: float
    rings_2180: list[list[list[float]]]
    rings_4326: list[list[list[float]]]
    bbox_2180: tuple[float, float, float, float]

    def contains(self, x: float, y: float) -> bool:
        xmin, ymin, xmax, ymax = self.bbox_2180
        if not (xmin <= x <= xmax and ymin <= y <= ymax):
            return False
        inside = False
        for ring in self.rings_2180:
            j = len(ring) - 1
            for i in range(len(ring)):
                xi, yi = ring[i]
                xj, yj = ring[j]
                if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                    inside = not inside
                j = i
        return inside

    def as_answer(self) -> dict:
        return {
            "dzialka": self.dzialka,
            "numer": self.numer,
            "obreb": self.obreb,
            "gmina": self.gmina,
            "pow_ha": self.pow_ha,
            "obrys_4326": self.rings_4326,
        }


@lru_cache(maxsize=1)
def load_all() -> tuple[FrozenParcel, ...]:
    path = MAP_DIR / PARCELS_FILE
    if not path.is_file():
        return ()
    out = []
    for p in json.loads(path.read_text(encoding="utf-8"))["parcels"]:
        xs = [pt[0] for ring in p["rings_2180"] for pt in ring]
        ys = [pt[1] for ring in p["rings_2180"] for pt in ring]
        out.append(
            FrozenParcel(
                dzialka=p["dzialka"],
                numer=p["numer"],
                obreb=p["obreb"],
                gmina=p["gmina"],
                pow_ha=p["pow_ha"],
                rings_2180=p["rings_2180"],
                rings_4326=p["rings_4326"],
                bbox_2180=(min(xs), min(ys), max(xs), max(ys)),
            )
        )
    return tuple(out)


def _to_2180(lon: float, lat: float) -> tuple[float, float]:
    if not hasattr(_local, "t"):
        _local.t = Transformer.from_crs(4326, 2180, always_xy=True)
    return _local.t.transform(lon, lat)


def find(lon: float, lat: float) -> FrozenParcel | None:
    """The frozen parcel that contains the WGS84 point, or None."""
    x, y = _to_2180(lon, lat)
    for parcel in load_all():
        if parcel.contains(x, y):
            return parcel
    return None
