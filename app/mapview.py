"""The parcel photo with the SVG overlay: outline, outlet point, flow lines, ditches, numbered action markers.

Everything the overlay draws is converted from EPSG:2180 metres to the pixels of the orthophoto here, so the
template only prints coordinates. A layer that has nothing to draw is absent from the legend.
"""

from __future__ import annotations

import math
from urllib.parse import urlencode

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
LABEL_CHAR_W = 11.0  # approximate width of one character of the 19-unit label font, in image pixels
LABEL_H = 30.0
EDGE_MARGIN_PX = 1.5
MAX_NUDGE_PX = 4.0


class LegendRow(BaseModel):
    symbol: str  # css class of the symbol in "Warstwa na mapie": "outline", "line", "flow", "number"
    text: str
    n: int | None = None  # the action number for symbol "number"


class MapOverlay(MapView):
    """MapView plus what only the photo needs: basins, arrow heads, the outlet label and the legend rows."""

    basins_px: list[list[Point]] = []
    flow_heads_px: list[list[Point]] = []  # one triangle per flow line, at its end
    outlet_label: str = ""  # "zlewnia 12,4 ha"
    outlet_label_xy: Point | None = None  # top-left of the label's background box
    outlet_label_w: float = 0.0
    runoff_reason: str = ""  # shown instead of flow arrows: "spadek 0,3% jest za mały, …"
    slope_arrow_px: list[Point] = []  # tail and tip of the arrow along the fall, from the parcel's centre
    slope_head_px: list[Point] = []
    slope_label: str = ""  # "spadek 2,0%"
    slope_label_xy: Point | None = None
    slope_label_w: float = 0.0
    lower_edge_px: list[Point] = []  # the lower boundary segment, a thick line
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


def _flow_lines(ctx: ReportContext, width: int, height: int) -> list[list[Point]]:
    """Concentrated flow lines from the runoff analysis; none when the analysis gave a reason instead."""
    if ctx.runoff_reason:
        return []
    lines = []
    for line in ctx.flow_2180:
        px = [p for p in (to_px(ctx, x, y) for x, y in line) if p is not None]
        if len(px) >= 2 and _in_image(px, width, height):
            lines.append(px)
    return lines


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


def _outlet(ctx: ReportContext) -> Point | None:
    """The outlet of the runoff analysis; the lowest point of the outline when there is none."""
    if ctx.outlet_2180 is not None:
        return to_px(ctx, *ctx.outlet_2180)
    terrain = ctx.data.terrain.data if ctx.data.terrain.usable else None
    if terrain and terrain.lowest_outline_point_2180:
        return to_px(ctx, *terrain.lowest_outline_point_2180)
    return None


SLOPE_ARROW_PX = 70.0
NO_SLOPE_SENTENCE = "spadek działki nie jest wyznaczony: brak modelu terenu dla tej działki"


def _slope_arrow(ctx: ReportContext, outline: list[Point]) -> list[Point]:
    """Tail (centre of the outline's box) and tip of the arrow that points downhill; empty when the fall is unknown."""
    if ctx.downhill_deg is None:
        return []
    xs, ys = [p[0] for p in outline], [p[1] for p in outline]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    az = math.radians(ctx.downhill_deg)  # 0 north = up on the photo, 90 east = right
    dx, dy = math.sin(az), -math.cos(az)
    half = SLOPE_ARROW_PX / 2
    return [
        (round(cx - dx * half, 1), round(cy - dy * half, 1)),
        (round(cx + dx * half, 1), round(cy + dy * half, 1)),
    ]


def _lower_edge_px(ctx: ReportContext, width: int, height: int) -> list[Point]:
    if ctx.downhill_deg is None:
        return []
    px = [p for p in (to_px(ctx, x, y) for x, y in ctx.lower_edge_2180) if p is not None]
    return px if len(px) >= 2 and _in_image(px, width, height) else []


def _box(text: str, anchor: Point, offset: Point, width: int, height: int) -> tuple[Point, float]:
    """Top-left of a label box next to `anchor`, moved so that the box stays inside the photo."""
    w = round(len(text) * LABEL_CHAR_W + 16, 1)
    x = min(max(4.0, anchor[0] + offset[0]), max(4.0, width - w - 4.0))
    y = min(max(4.0, anchor[1] + offset[1]), max(4.0, height - LABEL_H - 4.0))
    return (round(x, 1), round(y, 1)), w


def map_view(ctx: ReportContext) -> MapOverlay | None:
    o = ctx.data.ortho.data if ctx.data.ortho.usable else None
    if o is None:
        return None
    outline = [[(float(c), float(r)) for c, r in ring] for ring in o.polygon_px]
    outlet = _outlet(ctx)
    flow = _flow_lines(ctx, o.width, o.height)
    arrow = _slope_arrow(ctx, outline[0])
    arrow_head_px = (arrow_head(arrow) or []) if arrow else []
    lower = _lower_edge_px(ctx, o.width, o.height)
    slope_label = f"spadek {dec(ctx.slope_pct, 1)}%" if arrow and ctx.slope_pct is not None else ""
    slope_label_xy, slope_label_w = (
        _box(slope_label, arrow[1], (12, -LABEL_H - 4), o.width, o.height) if slope_label else (None, 0.0)
    )
    reason = "" if arrow else (ctx.runoff_reason or NO_SLOPE_SENTENCE)
    heads = [h for h in (arrow_head(line) for line in flow) if h]
    ditches, basins = _water(ctx, o.width, o.height)
    markers = []
    for a in ctx.actions:
        if a.place is not None:
            px = a.place.px or to_px(ctx, a.place.x_2180, a.place.y_2180)
            if px:
                x, y = inside_outline(outline[0], px)
                markers.append(MapMarker(n=a.n, x=x, y=y, kind=a.place.kind))
    label = f"{ctx.parcel.number} · {ha(ctx.parcel.area_ha)}"
    outlet_label = (
        f"zlewnia {dec(ctx.outlet_catchment_ha, 1)} ha"
        if outlet and ctx.outlet_catchment_ha is not None
        else ""
    )
    outlet_label_xy, outlet_label_w = (
        _box(outlet_label, outlet, (20, -LABEL_H - 6), o.width, o.height)
        if outlet_label and outlet
        else (None, 0.0)
    )
    legend = [LegendRow(symbol="outline", text=f"obrys działki {label}")]
    if outlet and not any(m.kind == "punkt wypływu" for m in markers):
        legend.append(LegendRow(symbol="outlet", text="punkt wypływu"))
    if arrow:
        legend.append(LegendRow(symbol="slope", text="kierunek spadku"))
    if lower:
        legend.append(LegendRow(symbol="edge", text="dolny odcinek granicy"))
    if flow:
        legend.append(LegendRow(symbol="flow", text="linia spływu wody"))
    if ditches:
        legend.append(LegendRow(symbol="line", text="rów lub ciek (BDOT10k)"))
    if basins:
        legend.append(LegendRow(symbol="basin", text="zbiornik wodny (BDOT10k)"))
    legend += [LegendRow(symbol="number", text=m.kind, n=m.n) for m in markers]
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
        outlet_px=outlet,
        ditches_px=ditches,
        flow_px=flow,
        markers=markers,
        label=label,
        basins_px=basins,
        flow_heads_px=heads,
        outlet_label=outlet_label,
        outlet_label_xy=outlet_label_xy,
        outlet_label_w=outlet_label_w,
        runoff_reason=reason,
        slope_arrow_px=arrow,
        slope_head_px=arrow_head_px,
        slope_label=slope_label,
        slope_label_xy=slope_label_xy,
        slope_label_w=slope_label_w,
        lower_edge_px=lower,
        legend=legend,
        origin_2180=origin,
        corners_4326=[(round(lon, 7), round(lat, 7)) for lon, lat in corners],
    )
