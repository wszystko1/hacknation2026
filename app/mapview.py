"""The parcel photo with the SVG overlay: outline, ditches, candidate shapes, slope arrows, numbered pins.

Everything the overlay draws is converted from EPSG:2180 metres to the pixels of the orthophoto here, so the
template only prints coordinates. A layer that has nothing to draw is absent from the legend.
"""

from __future__ import annotations

import math
from urllib.parse import urlencode

import numpy as np
from pydantic import BaseModel
from pyproj import Transformer

from app.context import ReportContext
from app.fmt import dec, ha
from app.geodata.models import WaterFeature
from app.models import MapMarker, MapView

Point = tuple[float, float]
LINE_KINDS = {"ditch", "stream", "canal"}  # drawn as lines in mo-ditch; "water_body" is drawn as a basin
ARROW_LEN = 16.0
ARROW_HALF_WIDTH = 7.0
MAIN_ARROW_LEN = 56.0  # screen px
GRID_MIN, GRID_MAX = 6, 12  # small local-fall arrows in the outline
ARROW_MIN_PX, ARROW_MAX_PX = 10.0, 28.0
GRADIENT_RESOLUTION_PCT = 0.1  # below this the height model cannot give a direction
FLAT_PCT = 1.0  # below this the arrows are drawn lighter and the label says "teren płaski"
PIN_CLEAR_PX = 30.0  # small arrows keep this far from a pin (photo pixels)
EDGE_MARGIN_PX = 1.5
MAX_NUDGE_PX = 4.0


class LegendRow(BaseModel):
    symbol: str  # css class of the legend symbol: "outline", "slope", "line", "pin"
    text: str


class SlopeArrow(BaseModel):
    """A slope arrow of fixed screen length: placed at (x, y) of the photo, turned by `angle` (degrees, clockwise
    from east in the SVG's y-down space), `length` px long on the screen at any zoom (app/static/maplayers.js)."""

    x: float
    y: float
    angle: float
    length: float


class Shape(BaseModel):
    """A candidate's geometry in photo pixels: a line (strip, balk) or a filled polygon (depression, pond)."""

    n: int
    kind: str  # "line" or "polygon"
    points: list[tuple[float, float]]
    rows: list[tuple[float, float]] = []  # tillage across the slope: a short line along the rows, through the pin


class MapOverlay(MapView):
    """MapView plus what only the photo needs: candidate shapes, slope arrows, the label and the legend rows."""

    basins_px: list[list[Point]] = []
    shapes: list[Shape] = []
    runoff_reason: str = ""  # one sentence for a flat parcel: what the flatness means for the farmer
    slope_main: SlopeArrow | None = None  # the plane's direction of the fall, one per map
    slope_grid: list[SlopeArrow] = []  # 6-12 small arrows of the local fall from the terrain model
    slope_flat: bool = False  # slope below the usual threshold: lighter and thinner arrows
    slope_label: str = ""  # "spadek 2,9%" or "Teren płaski · spadek 0,5%"
    legend: list[LegendRow] = []
    # What a click on the photo needs to turn a pixel into a point on the earth (app/static/neighbour.js):
    origin_2180: Point = (0.0, 0.0)  # EPSG:2180 (x, y) of pixel (0, 0), the top-left corner
    corners_4326: list[
        Point
    ] = []  # (lon, lat) of the top-left, top-right and bottom-left corner of the photo


_TO_4326 = Transformer.from_crs(2180, 4326, always_xy=True)


def px_to_2180(view: MapOverlay, col: float, row: float) -> Point:
    """Pixel (column, row) of the photo -> EPSG:2180 metres: the inverse of to_px."""
    return view.origin_2180[0] + col * view.m_per_px, view.origin_2180[1] - row * view.m_per_px


def px_to_lonlat(view: MapOverlay, col: float, row: float) -> Point:
    """Pixel -> (lon, lat) by the affine map through the photo's three corners, the same arithmetic as neighbour.js.

    The photo is about a kilometre wide; over that distance the difference to the exact projection is centimetres.
    """
    (lon0, lat0), (lon1, lat1), (lon2, lat2) = view.corners_4326
    u, v = col / view.width, row / view.height
    return lon0 + u * (lon1 - lon0) + v * (lon2 - lon0), lat0 + u * (lat1 - lat0) + v * (lat2 - lat0)


def to_px(ctx: ReportContext, x: float, y: float) -> Point | None:
    """EPSG:2180 metres -> pixel (column, row) of the orthophoto, origin top-left."""
    o = ctx.data.ortho.data
    if o is None:
        return None
    xmin, _, _, ymax = o.bbox_2180
    return round((x - xmin) / o.m_per_px, 1), round((ymax - y) / o.m_per_px, 1)


def _ring_px(ctx: ReportContext, ring: list[list[float]]) -> list[Point]:
    return [p for p in (to_px(ctx, x, y) for x, y in ring) if p is not None]


def _in_image(points: list[Point], width: int, height: int) -> bool:
    return any(0 <= x <= width and 0 <= y <= height for x, y in points)


def arrow_head(line: list[Point]) -> list[Point] | None:
    """Triangle at the last point of a polyline, pointing along its last non-degenerate segment."""
    tip = line[-1]
    for x, y in reversed(line[:-1]):
        dx, dy = tip[0] - x, tip[1] - y
        length = math.hypot(dx, dy)
        if length >= 1.0:
            ux, uy = dx / length, dy / length
            bx, by = tip[0] - ux * ARROW_LEN, tip[1] - uy * ARROW_LEN
            nx, ny = -uy * ARROW_HALF_WIDTH, ux * ARROW_HALF_WIDTH
            return [tip, (round(bx + nx, 1), round(by + ny, 1)), (round(bx - nx, 1), round(by - ny, 1))]
    return None


def _inside(ring: list[Point], p: Point) -> bool:
    x, y = p
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1], strict=True):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _nearest_edge(ring: list[Point], p: Point) -> tuple[float, Point]:
    """(distance to the outline, unit vector along the nearest edge)."""
    best, along = math.inf, (1.0, 0.0)
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1], strict=True):
        dx, dy = x2 - x1, y2 - y1
        length2 = dx * dx + dy * dy
        t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((p[0] - x1) * dx + (p[1] - y1) * dy) / length2))
        d = math.hypot(p[0] - (x1 + t * dx), p[1] - (y1 + t * dy))
        if d < best and length2 > 0:
            best, along = d, (dx / math.sqrt(length2), dy / math.sqrt(length2))
    return best, along


def _edge_distance(ring: list[Point], p: Point) -> float:
    return _nearest_edge(ring, p)[0]


def inside_outline(ring: list[Point], p: Point) -> Point:
    """The point itself when it lies at least EDGE_MARGIN_PX inside the outline; else moved off the nearest edge.

    An outlet is found on the boundary; its marker belongs on the parcel, a few metres in. The move is at most
    MAX_NUDGE_PX pixels (about 8 m at 2 m per pixel), perpendicular to the nearest edge and towards the inside;
    a point that cannot get inside that way stays where it is.
    """
    if _inside(ring, p) and _edge_distance(ring, p) >= EDGE_MARGIN_PX:
        return p
    _, (ux, uy) = _nearest_edge(ring, p)
    for nx, ny in ((-uy, ux), (uy, -ux)):
        if not _inside(ring, (p[0] + nx * MAX_NUDGE_PX, p[1] + ny * MAX_NUDGE_PX)):
            continue
        for step in range(1, int(MAX_NUDGE_PX / 0.5) + 1):
            q = (round(p[0] + nx * step * 0.5, 1), round(p[1] + ny * step * 0.5, 1))
            if _inside(ring, q) and _edge_distance(ring, q) >= EDGE_MARGIN_PX:
                return q
    return p


NO_SLOPE_SENTENCE = "spadek działki nie jest wyznaczony: brak modelu terenu dla tej działki"


def _water(ctx: ReportContext, width: int, height: int) -> tuple[list[list[Point]], list[list[Point]]]:
    """(ditches, streams and canals as lines; water bodies as basins) that touch the photo."""
    water = ctx.data.water.data if ctx.data.water.usable else None
    if water is None:
        return [], []
    lines: list[list[Point]] = []
    basins: list[list[Point]] = []
    feature: WaterFeature
    for feature in water.features:
        for ring in feature.rings_2180:
            px = _ring_px(ctx, ring)
            if len(px) < 3 or not _in_image(px, width, height):
                continue
            (lines if feature.kind in LINE_KINDS else basins).append(px)
    return lines, basins


def _ring_center(ring: list[Point]) -> Point:
    """A point well inside the outline: the lattice point farthest from the edge (a centroid can lie outside)."""
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    best, best_p = -1.0, (sum(xs) / len(xs), sum(ys) / len(ys))
    steps = 24
    for i in range(steps + 1):
        for j in range(steps + 1):
            q = (min(xs) + (max(xs) - min(xs)) * i / steps, min(ys) + (max(ys) - min(ys)) * j / steps)
            if _inside(ring, q):
                d = _edge_distance(ring, q)
                if d > best:
                    best, best_p = d, q
    return round(best_p[0], 1), round(best_p[1], 1)


def _angle(deg_from_north: float) -> float:
    """Azimuth (0 north = up, 90 east = right) -> SVG rotation (0 = pointing right, clockwise)."""
    return round((deg_from_north - 90.0) % 360.0, 1)


def _grid_of(ctx: ReportContext):
    terrain = ctx.data.terrain.data if ctx.data.terrain.usable else None
    if terrain is None:
        return None
    return terrain.grid or terrain.catchment_grid


def _local_fall(grid, x: float, y: float, smooth: int = 2) -> tuple[float, float] | None:
    """(slope in %, azimuth of the fall) at an EPSG:2180 point from a box-smoothed height model; None without heights."""
    z = np.array(grid.z, dtype=float).reshape(grid.rows, grid.cols)
    col = int((x - grid.x0) / grid.step_m)
    row = int((grid.y_top - y) / grid.step_m)
    r0, r1 = max(row - smooth, 0), min(row + smooth + 1, grid.rows)
    c0, c1 = max(col - smooth, 0), min(col + smooth + 1, grid.cols)
    if r1 - r0 < 3 or c1 - c0 < 3:
        return None
    block = z[r0:r1, c0:c1]
    if np.isnan(block).any():
        return None
    gy, gx = np.gradient(block, grid.step_m)  # gy: per row = towards the south; gx: towards the east
    dzdx, dzdy = float(gx.mean()), -float(gy.mean())  # y north
    pct = 100.0 * math.hypot(dzdx, dzdy)
    return pct, math.degrees(math.atan2(-dzdx, -dzdy)) % 360.0


def _lattice(ring: list[Point], avoid: list[Point]) -> list[Point]:
    """GRID_MIN..GRID_MAX points spread evenly inside the outline, away from the pins."""
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    area = abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1], strict=True))) / 2
    step = math.sqrt(max(area, 1.0) / 9.0)
    margin = min(6.0, 0.15 * math.sqrt(max(area, 1.0)))
    best: list[Point] = []
    for _ in range(40):
        pts: list[Point] = []
        x0 = (min(xs) + max(xs)) / 2 - step * round((max(xs) - min(xs)) / step / 2)
        y0 = (min(ys) + max(ys)) / 2 - step * round((max(ys) - min(ys)) / step / 2)
        gx = x0
        while gx <= max(xs):
            gy = y0
            while gy <= max(ys):
                q = (round(gx + step / 2, 1), round(gy + step / 2, 1))
                if _inside(ring, q) and _edge_distance(ring, q) >= margin:
                    pts.append(q)
                gy += step
            gx += step
        near = [q for q in pts if all(math.hypot(q[0] - a[0], q[1] - a[1]) >= PIN_CLEAR_PX for a in avoid)]
        use = near if len(near) >= GRID_MIN else pts
        best = use
        if GRID_MIN <= len(use) <= GRID_MAX:
            return use
        step *= 1.12 if len(use) > GRID_MAX else 0.9
    return best[:GRID_MAX]


def _arrow_length(slope_pct: float) -> float:
    return round(min(ARROW_MAX_PX, max(ARROW_MIN_PX, 10.0 + 4.0 * slope_pct)), 1)


def _slope_arrows(
    ctx: ReportContext, ring: list[Point], pins: list[Point]
) -> tuple[SlopeArrow | None, list[SlopeArrow]]:
    """The plane's arrow and the small local ones. Nothing when the fall is below what the height model resolves."""
    if ctx.downhill_deg is None or ctx.slope_pct is None or ctx.slope_pct < GRADIENT_RESOLUTION_PCT:
        return None, []
    cx, cy = _ring_center(ring)
    main = SlopeArrow(x=cx, y=cy, angle=_angle(ctx.downhill_deg), length=MAIN_ARROW_LEN)
    grid = _grid_of(ctx)
    small: list[SlopeArrow] = []
    for px in _lattice(ring, pins + [(cx, cy)]):
        az, pct = ctx.downhill_deg, ctx.slope_pct
        if grid is not None:
            o = ctx.data.ortho.data
            x2180 = o.bbox_2180[0] + px[0] * o.m_per_px
            y2180 = o.bbox_2180[3] - px[1] * o.m_per_px
            local = _local_fall(grid, x2180, y2180)
            if local is not None and local[0] >= GRADIENT_RESOLUTION_PCT:
                pct, az = local
        small.append(SlopeArrow(x=px[0], y=px[1], angle=_angle(az), length=_arrow_length(pct)))
    return main, small


def _shape_center(points: list[Point], kind: str) -> Point:
    if kind == "polygon":
        return round(sum(p[0] for p in points) / len(points), 1), round(sum(p[1] for p in points) / len(points), 1)
    total = sum(math.dist(a, b) for a, b in zip(points, points[1:], strict=False))
    run = 0.0
    for a, b in zip(points, points[1:], strict=False):
        d = math.dist(a, b)
        if run + d >= total / 2 and d > 0:
            t = (total / 2 - run) / d
            return round(a[0] + (b[0] - a[0]) * t, 1), round(a[1] + (b[1] - a[1]) * t, 1)
        run += d
    return points[0]


def _candidate_shape(ctx: ReportContext, a) -> tuple[Shape | None, Point | None]:
    """The drawn shape of an action's candidate and the pin position at its middle (None, None without geometry)."""
    g = a.candidate.geometry if a.candidate else None
    if g is None:
        return None, None
    px = [p for p in (to_px(ctx, x, y) for x, y in g.coordinates) if p is not None]
    if len(px) != len(g.coordinates):
        return None, None
    if g.type == "point":
        pin = px[0]
        rows: list[Point] = []
        if g.azimuth_deg is not None:
            az = math.radians(g.azimuth_deg)
            dx, dy = math.sin(az) * 30, -math.cos(az) * 30
            rows = [(round(pin[0] - dx, 1), round(pin[1] - dy, 1)), (round(pin[0] + dx, 1), round(pin[1] + dy, 1))]
        return (Shape(n=a.n, kind="point", points=px, rows=rows), pin)
    return Shape(n=a.n, kind=g.type, points=px), _shape_center(px, g.type)


def map_view(ctx: ReportContext) -> MapOverlay | None:
    o = ctx.data.ortho.data if ctx.data.ortho.usable else None
    if o is None:
        return None
    outline = [[(float(c), float(r)) for c, r in ring] for ring in o.polygon_px]
    ditches, basins = _water(ctx, o.width, o.height)
    markers, shapes = [], []
    for a in ctx.actions:
        shape, pin = _candidate_shape(ctx, a)
        if shape is not None:
            shapes.append(shape)
        if pin is None and a.place is not None:
            pin = a.place.px or to_px(ctx, a.place.x_2180, a.place.y_2180)
        if (pin is not None and (a.place is not None or shape is not None)):
            x, y = inside_outline(outline[0], pin) if shape is None or shape.kind == "point" else pin
            markers.append(MapMarker(n=a.n, x=x, y=y, kind=a.place.kind if a.place else a.title))
    main, small = _slope_arrows(ctx, outline[0], [(k.x, k.y) for k in markers])
    flat = ctx.slope_pct is not None and ctx.slope_pct < FLAT_PCT
    label = f"{ctx.parcel.number} · {ha(ctx.parcel.area_ha)}"
    slope_label = ""
    reason = ""
    if main is not None and ctx.slope_pct is not None:
        slope_label = f"Teren płaski · spadek {dec(ctx.slope_pct, 1)}%" if flat else f"spadek {dec(ctx.slope_pct, 1)}%"
        if flat:
            reason = (
                f"spadek {dec(ctx.slope_pct, 1)}% to teren płaski: woda nie spływa w jedną stronę, "
                "więc działania dotyczą całej działki, a nie jednego miejsca."
            )
    elif ctx.slope_pct is not None:
        slope_label = "teren płaski, kierunek spadku nieznaczący"
        reason = "teren płaski: kierunek spadku jest poniżej rozdzielczości modelu terenu, więc działania dotyczą całej działki."
    else:
        reason = ctx.runoff_reason or NO_SLOPE_SENTENCE
    legend = [LegendRow(symbol="outline", text=f"obrys {ctx.parcel.number}")]
    if main is not None:
        legend.append(LegendRow(symbol="slope", text="kierunek spadku"))
    if ditches or basins:
        legend.append(LegendRow(symbol="line", text="rów, ciek lub zbiornik"))
    if markers:
        legend.append(LegendRow(symbol="pin", text="miejsce działania"))
    origin = (o.bbox_2180[0], o.bbox_2180[3])
    corners = [
        _TO_4326.transform(origin[0] + col * o.m_per_px, origin[1] - row * o.m_per_px)
        for col, row in ((0, 0), (o.width, 0), (0, o.height))
    ]
    query = urlencode({"dzialka": ctx.request.parcel_id, "data": ctx.request.day.isoformat()})
    return MapOverlay(
        image_url=f"/raport/zdjecie?{query}",
        width=o.width,
        height=o.height,
        m_per_px=o.m_per_px,
        outline_px=outline,
        ditches_px=ditches,
        markers=markers,
        label=label,
        basins_px=basins,
        shapes=shapes,
        runoff_reason=reason,
        slope_main=main,
        slope_grid=small,
        slope_flat=flat,
        slope_label=slope_label,
        legend=legend,
        origin_2180=origin,
        corners_4326=[(round(lon, 7), round(lat, 7)) for lon, lat in corners],
    )
