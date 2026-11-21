"""The parcel photo with the SVG overlay: outline, outlet point, ditches, numbered action markers."""

from __future__ import annotations

from urllib.parse import urlencode

from app.context import ReportContext
from app.fmt import ha
from app.models import MapMarker, MapView


def to_px(ctx: ReportContext, x: float, y: float) -> tuple[float, float] | None:
    """EPSG:2180 metres -> pixel (column, row) of the orthophoto, origin top-left."""
    o = ctx.data.ortho.data
    if o is None:
        return None
    xmin, _, _, ymax = o.bbox_2180
    return round((x - xmin) / o.m_per_px, 1), round((ymax - y) / o.m_per_px, 1)


def map_view(ctx: ReportContext) -> MapView | None:
    o = ctx.data.ortho.data if ctx.data.ortho.usable else None
    if o is None:
        return None
    terrain = ctx.data.terrain.data if ctx.data.terrain.usable else None
    outlet = None
    if terrain and terrain.lowest_outline_point_2180:
        outlet = to_px(ctx, *terrain.lowest_outline_point_2180)
    markers = []
    for a in ctx.actions:
        if a.place is not None:
            px = a.place.px or to_px(ctx, a.place.x_2180, a.place.y_2180)
            if px:
                markers.append(MapMarker(n=a.n, x=px[0], y=px[1], kind=a.place.kind))
    query = urlencode({"dzialka": ctx.request.parcel_id, "data": ctx.request.day.isoformat()})
    return MapView(
        image_url=f"/raport/zdjecie?{query}",
        width=o.width,
        height=o.height,
        m_per_px=o.m_per_px,
        outline_px=[[(float(c), float(r)) for c, r in ring] for ring in o.polygon_px],
        outlet_px=outlet,
        markers=markers,
        label=f"{ctx.parcel.number} · {ha(ctx.parcel.area_ha)}",
    )
