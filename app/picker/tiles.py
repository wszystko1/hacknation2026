"""Map tiles for the parcel picker: 256 px XYZ tiles cut from the GUGiK WMS, cached on disk.

Order of sources for one tile: disk cache (data/raw, outside the repository), the frozen copy in demo/data/map/tiles,
the WMS. A tile that none of them can give is a flat grey one, so the browser logs no error.
"""

from __future__ import annotations

import math
import threading
import time
import warnings
from functools import lru_cache
from pathlib import Path

from app.geodata import cache, config, http
from app.geodata.errors import GeodataError
from app.picker.frozen import MAP_DIR
from app.picker.webmercator import TILE_PX, tile_bbox_3857

TOPO_WMS_URL = "https://mapy.geoportal.gov.pl/wss/service/img/guest/TOPO/MapServer/WMSServer"
LAYERS = {"podklad": TOPO_WMS_URL, "orto": config.ORTHO_WMS_URL}
MIN_ZOOM = 9
MAX_ZOOM = 19
# Frame of Poland (same as the picker map): lon 14.0-24.2, lat 49.0-54.9.
POLAND_LON = (14.0, 24.2)
POLAND_LAT = (49.0, 54.9)
_WMS_SLOTS = threading.BoundedSemaphore(4)
TILE_TIMEOUT_S = 8.0
MAX_TILE_BYTES = 1_000_000
FROZEN_TILES = MAP_DIR / "tiles"


def frozen_path(layer: str, z: int, x: int, y: int) -> Path:
    return FROZEN_TILES / layer / str(z) / str(x) / f"{y}.jpg"


def cache_path(layer: str, z: int, x: int, y: int) -> Path:
    return config.cache_dir() / "map_tiles" / layer / str(z) / str(x) / f"{y}.jpg"


@lru_cache(maxsize=1)
def placeholder() -> bytes:
    """A flat light-grey 256 px JPEG for tiles that are neither cached nor reachable."""
    import numpy as np
    import rasterio

    data = np.full((3, TILE_PX, TILE_PX), 235, dtype="uint8")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with rasterio.MemoryFile() as memory:
            with memory.open(
                driver="JPEG", width=TILE_PX, height=TILE_PX, count=3, dtype="uint8", QUALITY=60
            ) as ds:
                ds.write(data)
            return memory.read()


def _tile_xy(lon: float, lat: float, z: int) -> tuple[int, int]:
    n = 2**z
    x = int((lon + 180.0) / 360.0 * n)
    rad = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(rad)) / math.pi) / 2.0 * n)
    return x, y


def poland_range(z: int) -> tuple[int, int, int, int]:
    """(x_min, x_max, y_min, y_max) of the tiles that touch the frame of Poland at zoom z."""
    x0, y1 = _tile_xy(POLAND_LON[0], POLAND_LAT[0], z)
    x1, y0 = _tile_xy(POLAND_LON[1], POLAND_LAT[1], z)
    return x0, x1, y0, y1


def valid_address(layer: str, z: int, x: int, y: int) -> bool:
    if layer not in LAYERS or not MIN_ZOOM <= z <= MAX_ZOOM:
        return False
    x0, x1, y0, y1 = poland_range(z)
    return x0 <= x <= x1 and y0 <= y <= y1


def fetch_from_wms(layer: str, z: int, x: int, y: int) -> bytes | None:
    """JPEG bytes of the tile from the WMS, or None when it is unreachable or answers with anything but a JPEG."""
    bbox = ",".join(f"{v:.3f}" for v in tile_bbox_3857(z, x, y))
    params = {
        "SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetMap", "LAYERS": "Raster", "STYLES": "",
        "FORMAT": "image/jpeg", "SRS": "EPSG:3857", "BBOX": bbox, "WIDTH": str(TILE_PX), "HEIGHT": str(TILE_PX),
    }  # fmt: skip
    with _WMS_SLOTS:
        try:
            resp = http.get(
                LAYERS[layer],
                params=params,
                timeout=TILE_TIMEOUT_S,
                retries=1,
                deadline=time.monotonic() + 12,
                breaker=False,  # the WMS host also serves parcels: a slow tile must not block them
            )
        except GeodataError:
            return None
    if (
        resp.status_code != 200
        or not resp.content.startswith(b"\xff\xd8")
        or len(resp.content) > MAX_TILE_BYTES
    ):
        return None
    return resp.content


def get_tile(layer: str, z: int, x: int, y: int) -> tuple[bytes, bool]:
    """(JPEG bytes, real) where real is False for the grey stand-in."""
    for path in (cache_path(layer, z, x, y), frozen_path(layer, z, x, y)):
        if path.is_file():
            return path.read_bytes(), True
    if config.is_offline():
        return placeholder(), False
    image = fetch_from_wms(layer, z, x, y)
    if image is None:
        return placeholder(), False
    target = cache_path(layer, z, x, y)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f"{target.name}.{time.monotonic_ns()}.tmp")
        tmp.write_bytes(image)
        tmp.replace(target)
        cache.note_write(config.cache_dir() / "map_tiles", config.TILE_CACHE_MAX_BYTES)
    except OSError:
        pass  # a read-only disk only costs the cache
    return image, True
