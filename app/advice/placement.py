"""Where an action goes on the parcel, computed from its geometry (outline, elevation grid, BDOT10k water).

One function with typed input and output; the rule can be replaced without touching the rest of the report.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pyproj import Transformer

from app.geodata import ElevationGrid, WaterFeature
from app.models import Place

_TO_LONLAT = Transformer.from_crs("EPSG:2180", "EPSG:4326", always_xy=True)


@dataclass
class PlacementInput:
    outline_2180: list[list[float]]  # outer ring, [x, y] in EPSG:2180
    grid: ElevationGrid | None
    lowest_outline_point_2180: list[float] | None
    water: list[WaterFeature] = field(default_factory=list)
    slope_mean_pct: float | None = None


@dataclass
class PlaceCandidate:
    kind: str  # "punkt wypływu", "rów", "linia spływu", "zbiornik"
    place: Place | None
    reason: str = ""  # why there is no place ("teren płaski, spadek 0,3%")


def find_places(inp: PlacementInput) -> list[PlaceCandidate]:
    """Skeleton: the lowest point of the outline as the outlet; ditches and flow lines come next."""
    if inp.lowest_outline_point_2180 is None:
        return [PlaceCandidate(kind="punkt wypływu", place=None, reason="brak siatki wysokości dla działki")]
    x, y = inp.lowest_outline_point_2180
    lon, lat = _TO_LONLAT.transform(x, y)
    return [
        PlaceCandidate(
            kind="punkt wypływu",
            place=Place(
                kind="punkt wypływu",
                x_2180=x,
                y_2180=y,
                lon=lon,
                lat=lat,
                description="najniższy punkt obrysu",
            ),
        )
    ]
