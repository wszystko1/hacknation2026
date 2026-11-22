"""Detectors: from the terrain model and a mechanism row to a candidate with its place in EPSG:2180.

Four detectors find a place, one per mechanism family:

* `strip`: a line along the outflow segment of the outline (along the ditch when one runs by it);
* `balk`: a line across the slope through the middle of the parcel, clipped to the outline;
* `contour`: the polygon of cells whose slope lies in the catalogue's band, rows at right angles to the fall;
* `basin`: the largest depression (polygon) or, without one, the lowest interior point; refused near a road.

A plane that falls less than the smallest slope of the catalogue (0.5%) is below the resolution of the heights, so
the detectors give no geometry and say why. Mechanisms without a place on the map (`no_place`) become candidates
without a geometry that stay "potencjał do weryfikacji" with the reason from the mechanism table.

Every parameter is a `Range` with a unit and its source: a page of the cited document or "propozycja zespołu"
(the number is ours and is to be checked with an adviser). Nothing here reaches "wysoka" confidence: every
threshold is a proposal, not a measurement.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from app.advice import placement as pl
from app.advice.mechanisms import Mechanism
from app.advice.terrain_model import TerrainModel, _hull
from app.models import NO_PLACE_PREFIX, Candidate, Geometry, Range

PROPOSAL = "propozycja zespołu"
POTENTIAL = "potencjał do weryfikacji"

# Smallest distance (m) between a basin and a road. Team proposal: a basin that spills sooner floods the carriageway.
ROAD_MIN_M = 10.0
# A tillage polygon smaller than this many cells (100 m2 each) is a noise patch, not a field area.
MIN_TILLAGE_CELLS = 4
# Slope (%) below which the heights (rounded to 0.1 m) cannot tell a direction; used when the catalogue has no row.
DEFAULT_FLAT_PCT = 0.5

_AXIS_WORDS = (
    "z północy na południe",
    "z północnego wschodu na południowy zachód",
    "ze wschodu na zachód",
    "z południowego wschodu na północny zachód",
)


def _num(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def _flat_pct() -> float:
    value = pl._cond("pas-trawy-przy-wyplywie", "slope_min_pct")
    return DEFAULT_FLAT_PCT if value is None else value


def _no_place(mechanism: Mechanism, reason: str, **evidence: float | int | str | bool | None) -> Candidate:
    return Candidate(
        mechanism_id=mechanism.id,
        cause_codes=list(mechanism.causes_addressed),
        geometry=None,
        no_place_reason=f"{NO_PLACE_PREFIX}{reason}",
        evidence=dict(evidence),
        confidence="niska",
    )


def row_direction_words(azimuth_deg: float) -> str:
    """Rows along the axis with this azimuth, in words: 0 gives "z północy na południe"."""
    return _AXIS_WORDS[round((azimuth_deg % 180.0) / 45.0) % 4]


def rows_azimuth(downhill_deg: float) -> float:
    """Azimuth in [0, 180) of rows at right angles to the direction of the fall."""
    return round((downhill_deg + 90.0) % 180.0, 1) % 180.0


def _slope_check(model: TerrainModel, inp: pl.PlacementInput) -> tuple[pl.Plane | None, str]:
    """The fitted plane, or (None, reason) when there are no heights or the plane is too flat to name a direction."""
    if inp.grid is None:
        return None, "brak siatki wysokości dla działki"
    try:
        plane = pl.fit_plane(inp.grid)
    except ValueError:
        return None, "brak wysokości w siatce dla działki"
    slope = model.slope_pct if model.slope_pct is not None else plane.slope_pct
    if slope < _flat_pct():
        return None, f"spadek {pl._slope_text(slope)}% jest za mały, by wskazać kierunek spływu"
    return plane, ""


def _confidence(model: TerrainModel):
    """ "średnia" when the catchment was computed from the grid with a margin; otherwise "niska"."""
    return "średnia" if model.catchment_ha is not None else "niska"


# --------------------------------------------------------------------------------------------------------------
# strip
# --------------------------------------------------------------------------------------------------------------


def detect_strip(model: TerrainModel, mechanism: Mechanism, inp: pl.PlacementInput) -> Candidate:
    """A grass strip along the outflow segment; along the ditch when one runs within the catalogue's distance."""
    plane, why = _slope_check(model, inp)
    if plane is None:
        return _no_place(mechanism, why, slope_pct=model.slope_pct)
    seg = model.outflow
    if seg is None or len(seg.points_2180) < 2:
        return _no_place(
            mechanism,
            model.reason or "z działki nie wypływa woda w obrębie siatki",
            slope_pct=model.slope_pct,
        )
    ditch_max = pl._cond("pas-trawy-przy-wyplywie", "ditch_max_m")
    along = (
        ditch_max is not None and model.ditch_distance_m is not None and model.ditch_distance_m <= ditch_max
    )
    geometry = Geometry(type="line", coordinates=[(x, y) for x, y in seg.points_2180], length_m=seg.length_m)
    return Candidate(
        mechanism_id=mechanism.id,
        cause_codes=list(mechanism.causes_addressed),
        geometry=geometry,
        parameters={
            "szerokosc": Range(low=3.0, high=6.0, unit="m", source=PROPOSAL),
            "dlugosc": Range(low=round(seg.length_m * 0.8, 1), high=seg.length_m, unit="m", source=PROPOSAL),
        },
        evidence={
            "slope_pct": model.slope_pct,
            "outflow_share": seg.share,
            "catchment_ha": model.catchment_ha,
            "along_ditch": along,
            "ditch_distance_m": model.ditch_distance_m,
        },
        confidence=_confidence(model),
        risks=["pas zasypany namułem przestaje wyhamowywać spływ; wymaga koszenia i czyszczenia"],
        next_step="wytyczyć pas wzdłuż rowu" if along else "wytyczyć pas wzdłuż dolnego odcinka granicy",
    )


# --------------------------------------------------------------------------------------------------------------
# balk
# --------------------------------------------------------------------------------------------------------------


def _inside_ring(x: float, y: float, ring: Sequence[Sequence[float]]) -> bool:
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:], strict=False):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def _clip_line(
    ring: list[list[float]], px: float, py: float, dx: float, dy: float
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """The longest part inside the ring of the line through (px, py) with direction (dx, dy)."""
    ts: list[float] = []
    for (x1, y1), (x2, y2) in zip(ring, ring[1:], strict=False):
        ex, ey = x2 - x1, y2 - y1
        den = dx * ey - dy * ex
        if abs(den) < 1e-12:
            continue
        t = ((x1 - px) * ey - (y1 - py) * ex) / den
        u = ((x1 - px) * dy - (y1 - py) * dx) / den
        if 0.0 <= u <= 1.0:
            ts.append(t)
    ts.sort()
    best: tuple[float, float] | None = None
    for a, b in zip(ts, ts[1:], strict=False):
        mid = (a + b) / 2.0
        if b - a > 1e-6 and _inside_ring(px + mid * dx, py + mid * dy, ring):
            if best is None or b - a > best[1] - best[0]:
                best = (a, b)
    if best is None:
        return None
    a, b = best
    return (px + a * dx, py + a * dy), (px + b * dx, py + b * dy)


def detect_balk(model: TerrainModel, mechanism: Mechanism, inp: pl.PlacementInput) -> Candidate:
    """A balk across the slope through the middle of the parcel, clipped to the outline."""
    plane, why = _slope_check(model, inp)
    if plane is None:
        return _no_place(mechanism, why, slope_pct=model.slope_pct)
    centre = pl._interior_cell_near_centre(inp)
    if centre is None:
        return _no_place(mechanism, "w siatce nie ma komórek wewnątrz działki")
    azimuth = rows_azimuth(plane.downhill_deg)
    rad = math.radians(azimuth)
    clipped = _clip_line(inp.outline_2180, centre[0], centre[1], math.sin(rad), math.cos(rad))
    if clipped is None:
        return _no_place(mechanism, "linia w poprzek stoku nie mieści się w obrysie działki")
    (x1, y1), (x2, y2) = clipped
    length = round(math.hypot(x2 - x1, y2 - y1), 1)
    return Candidate(
        mechanism_id=mechanism.id,
        cause_codes=list(mechanism.causes_addressed),
        geometry=Geometry(
            type="line",
            coordinates=[(round(x1, 1), round(y1, 1)), (round(x2, 1), round(y2, 1))],
            azimuth_deg=azimuth,
            length_m=length,
        ),
        parameters={
            "szerokosc": Range(low=2.0, high=4.0, unit="m", source=PROPOSAL),
            "dlugosc": Range(low=length, high=length, unit="m", source=PROPOSAL),
        },
        evidence={"slope_pct": round(plane.slope_pct, 2), "downhill_deg": round(plane.downhill_deg, 1)},
        confidence=_confidence(model),
        risks=["miedza w poprzek stoku zatrzymuje wodę tylko przy spływie powierzchniowym, nie w rowie"],
        next_step="wytyczyć miedzę wzdłuż warstwicy",
    )


# --------------------------------------------------------------------------------------------------------------
# contour
# --------------------------------------------------------------------------------------------------------------


def _band_cells(inp: pl.PlacementInput, lo: float, hi: float | None) -> list[tuple[float, float]]:
    """Centres of the cells inside the parcel whose local slope (central differences, 2 cells apart) is in the band."""
    assert inp.grid is not None
    z = pl._heights(inp.grid)
    inside = pl._inside(inp.grid)
    gy, gx = np.gradient(z, inp.grid.step_m)
    slope = 100.0 * np.hypot(gx, gy)
    ok = inside & np.isfinite(slope) & (slope >= lo) & ((slope <= hi) if hi is not None else True)
    rows, cols = np.nonzero(ok)
    if not len(rows):
        return []
    xs, ys = pl._centres(inp.grid, rows, cols)
    return [(float(x), float(y)) for x, y in zip(xs, ys, strict=True)]


def detect_contour(model: TerrainModel, mechanism: Mechanism, inp: pl.PlacementInput) -> Candidate:
    """The area where the slope is in the catalogue's band, with rows at right angles to the fall."""
    plane, why = _slope_check(model, inp)
    if plane is None:
        return _no_place(mechanism, why, slope_pct=model.slope_pct)
    lo = pl._cond("uprawa-w-poprzek-stoku", "slope_min_pct")
    hi = pl._cond("uprawa-w-poprzek-stoku", "slope_max_pct")
    if lo is None:
        return _no_place(mechanism, "katalog nie podaje przedziału spadku dla uprawy w poprzek stoku")
    cells = _band_cells(inp, lo, hi)
    hull = _hull_of(cells)
    if len(cells) < MIN_TILLAGE_CELLS or len(hull) < 3:
        band = f"{_num(lo, 0)}–{_num(hi, 0)}%" if hi is not None else f"od {_num(lo, 0)}%"
        return _no_place(
            mechanism,
            f"spadek {pl._slope_text(plane.slope_pct)}% leży poza przedziałem {band}, w którym uprawa "
            "w poprzek stoku ma sens",
            slope_pct=round(plane.slope_pct, 2),
        )
    azimuth = rows_azimuth(plane.downhill_deg)
    area_ha = round(len(cells) * inp.grid.step_m**2 / 10_000.0, 2) if inp.grid else None
    words = row_direction_words(azimuth)
    return Candidate(
        mechanism_id=mechanism.id,
        cause_codes=list(mechanism.causes_addressed),
        geometry=Geometry(
            type="polygon",
            coordinates=[(round(x, 1), round(y, 1)) for x, y in hull],
            azimuth_deg=azimuth,
        ),
        parameters={
            "przedzial_spadku": Range(low=lo, high=hi if hi is not None else lo, unit="%", source=PROPOSAL),
        },
        evidence={
            "slope_pct": round(plane.slope_pct, 2),
            "downhill_deg": round(plane.downhill_deg, 1),
            "rows_words": words,
            "area_ha": area_ha,
        },
        confidence=_confidence(model),
        risks=["na spadku powyżej górnego progu rzędy w poprzek stoku mogą się przerywać"],
        next_step=f"siej i orz rzędami {words}",
    )


def _hull_of(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    return _hull(points)


# --------------------------------------------------------------------------------------------------------------
# basin
# --------------------------------------------------------------------------------------------------------------


def _distance_to_polyline(x: float, y: float, line: Sequence[Sequence[float]]) -> float:
    best = math.inf
    for (x1, y1), (x2, y2) in zip(line, line[1:], strict=False):
        ex, ey = x2 - x1, y2 - y1
        t = (
            0.0
            if ex == ey == 0
            else max(0.0, min(1.0, ((x - x1) * ex + (y - y1) * ey) / (ex * ex + ey * ey)))
        )
        best = min(best, math.hypot(x - x1 - t * ex, y - y1 - t * ey))
    return best


def road_distance(
    points: Sequence[Sequence[float]], roads: Sequence[Sequence[Sequence[float]]]
) -> float | None:
    """Smallest distance (m) from the points to the road lines; None without roads."""
    if not roads:
        return None
    return min(_distance_to_polyline(p[0], p[1], r) for p in points for r in roads if len(r) > 1)


def detect_basin(
    model: TerrainModel,
    mechanism: Mechanism,
    inp: pl.PlacementInput,
    roads: Sequence[Sequence[Sequence[float]]] = (),
) -> Candidate:
    """The largest depression deep enough, else the lowest interior point. A place within ROAD_MIN_M of a road is
    refused. `roads` are polylines in EPSG:2180."""
    depth_min = pl._cond("niecka-przy-wyplywie", "depression_min_m") or 0.2
    params = {
        "glebokosc_progu": Range(low=depth_min, high=depth_min, unit="m", source=PROPOSAL),
        "odleglosc_od_drogi": Range(low=ROAD_MIN_M, high=ROAD_MIN_M, unit="m", source=PROPOSAL),
    }
    refused: list[float] = []
    pits = [d for d in model.depressions if d.depth_m >= depth_min - 1e-9]
    for pit in pits:
        ring = [(x, y) for x, y in pit.outline_2180]
        if len(ring) > 1 and ring[0] == ring[-1]:
            ring = ring[:-1]
        if len(ring) < 3:
            continue
        dist = road_distance([*ring, tuple(pit.lowest_point_2180)], roads)
        if dist is not None and dist < ROAD_MIN_M:
            refused.append(dist)
            continue
        return Candidate(
            mechanism_id=mechanism.id,
            cause_codes=list(mechanism.causes_addressed),
            geometry=Geometry(type="polygon", coordinates=ring),
            parameters=params,
            evidence={
                "depth_m": pit.depth_m,
                "volume_m3": pit.volume_m3,
                "area_m2": pit.area_m2,
                "lowest_x": pit.lowest_point_2180[0],
                "lowest_y": pit.lowest_point_2180[1],
                "road_distance_m": None if dist is None else round(dist, 1),
            },
            confidence=_confidence(model),
            risks=["woda stojąca dłużej niż kilka dni szkodzi uprawie; sprawdź przepuszczalność gleby"],
            next_step="sprawdzić w terenie, czy zagłębienie zatrzymuje wodę po opadzie",
        )
    if refused:
        return _no_place(
            mechanism,
            f"zagłębienie leży {_num(min(refused), 0)} m od drogi, bliżej niż {_num(ROAD_MIN_M, 0)} m, "
            "i woda zalewałaby jezdnię",
            road_distance_m=round(min(refused), 1),
        )
    low = model.lowest_interior_2180
    if low is None:
        return _no_place(
            mechanism,
            model.reason or "w siatce nie ma zagłębienia ani najniższego punktu wnętrza działki",
        )
    dist = road_distance([low], roads)
    if dist is not None and dist < ROAD_MIN_M:
        return _no_place(
            mechanism,
            f"najniższy punkt wnętrza leży {_num(dist, 0)} m od drogi, bliżej niż {_num(ROAD_MIN_M, 0)} m",
            road_distance_m=round(dist, 1),
        )
    return Candidate(
        mechanism_id=mechanism.id,
        cause_codes=list(mechanism.causes_addressed),
        geometry=Geometry(type="point", coordinates=[(low[0], low[1])]),
        parameters=params,
        evidence={"no_depression": True, "road_distance_m": None if dist is None else round(dist, 1)},
        confidence="niska",
        risks=["to najniższy punkt wnętrza, nie zagłębienie z siatki; sprawdź w terenie, czy woda tu stoi"],
        next_step="sprawdzić w terenie, czy woda tu stoi po opadzie",
    )


# --------------------------------------------------------------------------------------------------------------
# no place on the map
# --------------------------------------------------------------------------------------------------------------


def potential_without_place(mechanism: Mechanism) -> Candidate:
    """A mechanism with no spot on the map (weir, drain regulator, mulch, soil capacity, irrigation)."""
    return Candidate(
        mechanism_id=mechanism.id,
        cause_codes=list(mechanism.causes_addressed),
        geometry=None,
        no_place_reason=f"{NO_PLACE_PREFIX}{mechanism.no_place_reason}",
        evidence={"potential": True},
        confidence="niska",
        next_step=f"{POTENTIAL}: {mechanism.opportunity_required}",
    )


def detect(
    mechanism: Mechanism,
    model: TerrainModel,
    inp: pl.PlacementInput,
    roads: Sequence[Sequence[Sequence[float]]] = (),
) -> Candidate:
    """The candidate of one mechanism, by the detector named in its row."""
    match mechanism.detector:
        case "strip":
            return detect_strip(model, mechanism, inp)
        case "balk":
            return detect_balk(model, mechanism, inp)
        case "contour":
            return detect_contour(model, mechanism, inp)
        case "basin":
            return detect_basin(model, mechanism, inp, roads)
        case _:
            return potential_without_place(mechanism)
