"""XYZ tile arithmetic for the Web Mercator grid (EPSG:3857), 256 px tiles."""

from __future__ import annotations

import math

TILE_PX = 256
HALF_WORLD_M = 20037508.342789244  # half of the circumference of the Web Mercator square


def tile_bbox_3857(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """(xmin, ymin, xmax, ymax) in metres of tile z/x/y; y counts from the top like in XYZ URLs."""
    size = 2 * HALF_WORLD_M / (2**z)
    xmin = -HALF_WORLD_M + x * size
    ymax = HALF_WORLD_M - y * size
    return xmin, ymax - size, xmin + size, ymax


def lonlat_to_tile(lon: float, lat: float, z: int) -> tuple[int, int]:
    """Tile that contains the WGS84 point."""
    n = 2**z
    lat = max(min(lat, 85.0511287798), -85.0511287798)
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
    return min(max(x, 0), n - 1), min(max(y, 0), n - 1)


def tile_range(z: int, west: float, south: float, east: float, north: float) -> tuple[range, range]:
    """Columns and rows of the tiles that cover a WGS84 bounding box."""
    x0, y0 = lonlat_to_tile(west, north, z)
    x1, y1 = lonlat_to_tile(east, south, z)
    return range(x0, x1 + 1), range(y0, y1 + 1)
