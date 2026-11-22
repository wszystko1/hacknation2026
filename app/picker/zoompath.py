"""The zoom path of the demo: which tiles the map shows from the view of Poland down to a demo parcel.

The frozen copy in demo/data/map holds exactly these tiles, so the demo area works without a network.
"""

from __future__ import annotations

import math

from app.picker.webmercator import TILE_PX

VIEW_W, VIEW_H = 1366, 768  # map window of the demo browser, px
FIRST_ZOOM, LAST_ZOOM = 9, 17
ORTHO_FROM_ZOOM = 9  # the base map below this zoom (the map cannot be zoomed out that far), the orthophoto from it

POLAND_CENTRE = (19.15, 52.05)  # lon, lat of the view of Poland at FIRST_ZOOM
# Centroids (lon, lat) of the two demo parcels: 040303_2.0002.189/13 and 100403_2.0011.144.
DEMO_CENTRES = {
    "040303_2.0002.189/13": (18.1350276, 53.2705072),
    "100403_2.0011.144": (19.3503128, 52.0993747),
}


def layer_for_zoom(z: int) -> str:
    return "orto" if z >= ORTHO_FROM_ZOOM else "podklad"


def window_tiles(lon: float, lat: float, z: int) -> list[tuple[int, int]]:
    """Tiles that cover a VIEW_W x VIEW_H window centred on the point."""
    n = 2**z
    cx = (lon + 180.0) / 360.0 * n
    lat_r = math.radians(lat)
    cy = (1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * n
    half_w, half_h = VIEW_W / 2 / TILE_PX, VIEW_H / 2 / TILE_PX
    x0, x1 = math.floor(cx - half_w), math.floor(cx + half_w)
    y0, y1 = math.floor(cy - half_h), math.floor(cy + half_h)
    return [
        (x, y) for x in range(max(x0, 0), min(x1, n - 1) + 1) for y in range(max(y0, 0), min(y1, n - 1) + 1)
    ]


def path_tiles() -> list[tuple[str, int, int, int]]:
    """(layer, z, x, y) of every tile of the zoom path, sorted, without duplicates."""
    out: set[tuple[str, int, int, int]] = set()
    for x, y in window_tiles(*POLAND_CENTRE, FIRST_ZOOM):
        out.add((layer_for_zoom(FIRST_ZOOM), FIRST_ZOOM, x, y))
    for lon, lat in DEMO_CENTRES.values():
        for z in range(FIRST_ZOOM + 1, LAST_ZOOM + 1):
            for x, y in window_tiles(lon, lat, z):
                out.add((layer_for_zoom(z), z, x, y))
    return sorted(out)
