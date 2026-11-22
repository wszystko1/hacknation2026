"""Detectors: from the terrain model and a mechanism row to a candidate with its place in EPSG:2180.

Four detectors find a place, one per mechanism family:

* `strip`: a line along the outflow segment of the outline (along the ditch when one runs by it);
* `balk`: a contour line (isoline of the height grid) through the parcel, clipped to the outline, smoothed;
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
# Upper end (%) of the slope for contour farming in NRCS Practice Standard 330; the catalogue's band is wider.
NRCS_CONTOUR_MAX_PCT = 10.0
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


# Heights of the parcel's own cells needed before a contour line means anything (share of the cells inside the
# outline that have a height). Team proposal: with fewer, the line would be drawn through the gaps.
MIN_HEIGHT_SHARE = 0.8
# Shortest balk (m) worth marking out. Team proposal.
MIN_BALK_M = 20.0
# Levels tried for the balk, as quantiles of the heights inside the parcel; the longest line wins.
BALK_LEVEL_QUANTILES = (0.35, 0.42, 0.5, 0.58, 0.65)
# Tolerance (m) of the line simplification: a tenth of the 10 m grid, below the accuracy of the heights.
SIMPLIFY_M = 1.0


def _edge_point(grid, z: np.ndarray, level: float, edge: tuple[str, int, int]) -> tuple[float, float]:
    """The point where the level crosses a grid edge: ("h", r, c) joins (r, c)-(r, c+1), ("v", r, c) (r, c)-(r+1, c)."""
    kind, r, c = edge
    r2, c2 = (r, c + 1) if kind == "h" else (r + 1, c)
    z1, z2 = float(z[r, c]), float(z[r2, c2])
    t = (level - z1) / (z2 - z1)
    x1, y1 = grid.x0 + (c + 0.5) * grid.step_m, grid.y_top - (r + 0.5) * grid.step_m
    x2, y2 = grid.x0 + (c2 + 0.5) * grid.step_m, grid.y_top - (r2 + 0.5) * grid.step_m
    return x1 + t * (x2 - x1), y1 + t * (y2 - y1)


def isolines(grid, level: float) -> list[list[tuple[float, float]]]:
    """Polylines where the surface of the grid crosses `level` (marching squares on the cell centres).

    A square with a missing height at any corner is skipped, so a gap cuts a line in two instead of bridging it.
    Closed lines come back with the first point repeated at the end."""
    z = pl._heights(grid)
    up = z >= level
    known = np.isfinite(z)
    links: dict[tuple[str, int, int], list[tuple[str, int, int]]] = {}

    def link(a: tuple[str, int, int], b: tuple[str, int, int]) -> None:
        links.setdefault(a, []).append(b)
        links.setdefault(b, []).append(a)

    for r in range(grid.rows - 1):
        for c in range(grid.cols - 1):
            if not (known[r, c] and known[r, c + 1] and known[r + 1, c] and known[r + 1, c + 1]):
                continue
            tl, tr, bl, br = up[r, c], up[r, c + 1], up[r + 1, c], up[r + 1, c + 1]
            # the four edges of the square: top, right, bottom, left
            top, right, bottom, left = ("h", r, c), ("v", r, c + 1), ("h", r + 1, c), ("v", r, c)
            crossing = [
                e
                for e, flip in ((top, tl != tr), (right, tr != br), (bottom, bl != br), (left, tl != bl))
                if flip
            ]
            if len(crossing) == 2:
                link(crossing[0], crossing[1])
            elif len(crossing) == 4:  # a saddle: the mean of the corners says which two corners are joined
                centre_up = (z[r, c] + z[r, c + 1] + z[r + 1, c] + z[r + 1, c + 1]) / 4.0 >= level
                if centre_up == bool(tl):
                    link(top, right)
                    link(bottom, left)
                else:
                    link(top, left)
                    link(bottom, right)
    lines: list[list[tuple[float, float]]] = []
    seen: set[tuple[str, int, int]] = set()
    # open lines first (they start at a node with one link), then what is left is closed
    order = sorted(links, key=lambda e: (len(links[e]) != 1, e))
    for start in order:
        if start in seen:
            continue
        chain = [start]
        seen.add(start)
        prev, cur = None, start
        while True:
            nxt = next((n for n in links[cur] if n != prev and n not in seen), None)
            if nxt is None:
                if (
                    len(links[cur]) == 2
                    and links[cur][0] != links[cur][1]
                    and start in links[cur]
                    and len(chain) > 2
                ):
                    chain.append(start)  # closed
                break
            chain.append(nxt)
            seen.add(nxt)
            prev, cur = cur, nxt
        lines.append([_edge_point(grid, z, level, e) for e in chain])
    return lines


def _clip_polyline(
    line: Sequence[tuple[float, float]], ring: Sequence[Sequence[float]]
) -> list[list[tuple[float, float]]]:
    """The parts of the polyline inside the ring; each part starts and ends on the outline or at an end of the line."""
    parts: list[list[tuple[float, float]]] = []
    cur: list[tuple[float, float]] = []
    for (x1, y1), (x2, y2) in zip(line, line[1:], strict=False):
        dx, dy = x2 - x1, y2 - y1
        ts = [0.0, 1.0]
        for (ax, ay), (bx, by) in zip(ring, ring[1:], strict=False):
            ex, ey = bx - ax, by - ay
            den = dx * ey - dy * ex
            if abs(den) < 1e-12:
                continue
            t = ((ax - x1) * ey - (ay - y1) * ex) / den
            u = ((ax - x1) * dy - (ay - y1) * dx) / den
            if 0.0 < t < 1.0 and 0.0 <= u <= 1.0:
                ts.append(t)
        ts.sort()
        for t1, t2 in zip(ts, ts[1:], strict=False):
            if t2 - t1 < 1e-9:
                continue
            tm = (t1 + t2) / 2.0
            a = (x1 + t1 * dx, y1 + t1 * dy)
            b = (x1 + t2 * dx, y1 + t2 * dy)
            if _inside_ring(x1 + tm * dx, y1 + tm * dy, ring):
                if not cur:
                    cur = [a]
                elif math.hypot(cur[-1][0] - a[0], cur[-1][1] - a[1]) > 1e-6:
                    parts.append(cur)
                    cur = [a]
                cur.append(b)
            elif cur:
                parts.append(cur)
                cur = []
    if cur:
        parts.append(cur)
    return [p for p in parts if len(p) >= 2]


def _length(line: Sequence[tuple[float, float]]) -> float:
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(line, line[1:], strict=False))


def _smooth(line: list[tuple[float, float]], rounds: int = 2) -> list[tuple[float, float]]:
    """Chaikin corner cutting with both ends kept: the staircase of the grid becomes a gentle curve."""
    for _ in range(rounds):
        if len(line) < 3:
            return line
        out = [line[0]]
        for (x1, y1), (x2, y2) in zip(line, line[1:], strict=False):
            out.append((0.75 * x1 + 0.25 * x2, 0.75 * y1 + 0.25 * y2))
            out.append((0.25 * x1 + 0.75 * x2, 0.25 * y1 + 0.75 * y2))
        out[-1] = line[-1]
        line = out
    return line


def _simplify(line: list[tuple[float, float]], tolerance: float) -> list[tuple[float, float]]:
    """Douglas-Peucker."""
    if len(line) < 3:
        return line
    (x1, y1), (x2, y2) = line[0], line[-1]
    far, at = 0.0, 0
    for i, (x, y) in enumerate(line[1:-1], 1):
        d = _distance_to_polyline(x, y, [(x1, y1), (x2, y2)])
        if d > far:
            far, at = d, i
    if far <= tolerance:
        return [line[0], line[-1]]
    return _simplify(line[: at + 1], tolerance)[:-1] + _simplify(line[at:], tolerance)


def _balk_line(
    inp: pl.PlacementInput, z: np.ndarray, inside: np.ndarray
) -> tuple[float, list[tuple[float, float]]]:
    """(level, line): the longest piece inside the outline of the contour lines at a few levels around the median."""
    assert inp.grid is not None
    heights = z[inside & np.isfinite(z)]
    median = float(np.median(heights))
    best: tuple[float, float, list[tuple[float, float]]] | None = (
        None  # (length, -distance from median, line)
    )
    best_level = median
    for q in BALK_LEVEL_QUANTILES:
        level = float(np.quantile(heights, q))
        for line in isolines(inp.grid, level):
            for part in _clip_polyline(line, inp.outline_2180):
                key = (_length(part), -abs(level - median))
                if best is None or key > (best[0], best[1]):
                    best = (key[0], key[1], part)
                    best_level = level
    if best is None:
        return median, []
    return best_level, best[2]


def detect_balk(model: TerrainModel, mechanism: Mechanism, inp: pl.PlacementInput) -> Candidate:
    """A balk along the contour line (isoline of the 10 m height grid) that runs through the parcel.

    The line is the longest piece inside the outline of the contour at a height near the median of the parcel,
    smoothed and simplified. The width is an orientation range, not a measurement: the cited manual names no width.
    No place: no grid, too few heights, a plane too flat to tell a direction, or no contour line of MIN_BALK_M."""
    if inp.grid is None:
        return _no_place(mechanism, "brak siatki wysokości dla działki", slope_pct=model.slope_pct)
    z, inside = pl._heights(inp.grid), pl._inside(inp.grid)
    if not inside.any():
        return _no_place(mechanism, "w siatce nie ma komórek wewnątrz działki")
    share = float(np.isfinite(z[inside]).mean())
    if share < MIN_HEIGHT_SHARE:
        return _no_place(
            mechanism,
            f"siatka ma wysokość tylko w {_num(100 * share, 0)}% komórek działki, za mało, by poprowadzić warstwicę",
            height_share=round(share, 2),
        )
    plane, why = _slope_check(model, inp)
    if plane is None:
        return _no_place(mechanism, why, slope_pct=model.slope_pct)
    level, raw = _balk_line(inp, z, inside)
    line = _simplify(_smooth(raw), SIMPLIFY_M) if raw else []
    length = round(_length(line), 1)
    if len(line) < 2 or length < MIN_BALK_M:
        return _no_place(
            mechanism,
            f"warstwica przez działkę ma {_num(length, 0)} m, mniej niż {_num(MIN_BALK_M, 0)} m",
            slope_pct=round(plane.slope_pct, 2),
        )
    (x1, y1), (x2, y2) = line[0], line[-1]
    azimuth = round(math.degrees(math.atan2(x2 - x1, y2 - y1)) % 180.0, 1) % 180.0
    return Candidate(
        mechanism_id=mechanism.id,
        cause_codes=list(mechanism.causes_addressed),
        geometry=Geometry(
            type="line",
            coordinates=[(round(x, 1), round(y, 1)) for x, y in line],
            azimuth_deg=azimuth,
            length_m=length,
        ),
        parameters={
            "szerokosc": Range(low=2.0, high=4.0, unit="m", source=PROPOSAL),
            "dlugosc": Range(low=length, high=length, unit="m", source=PROPOSAL),
        },
        evidence={
            "slope_pct": round(plane.slope_pct, 2),
            "downhill_deg": round(plane.downhill_deg, 1),
            "level_m": round(level, 2),
            "height_share": round(share, 2),
        },
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


def _clip_to_convex(
    ring: Sequence[Sequence[float]], convex: Sequence[tuple[float, float]]
) -> list[tuple[float, float]]:
    """Sutherland-Hodgman: the ring clipped to a convex counter-clockwise polygon."""
    out = [(float(x), float(y)) for x, y in ring]
    if len(out) > 1 and out[0] == out[-1]:
        out = out[:-1]
    for (ax, ay), (bx, by) in zip(convex, [*convex[1:], convex[0]], strict=True):

        def side(p: tuple[float, float], ax=ax, ay=ay, bx=bx, by=by) -> float:
            return (bx - ax) * (p[1] - ay) - (by - ay) * (p[0] - ax)

        clipped: list[tuple[float, float]] = []
        for cur, nxt in zip(out, [*out[1:], out[0]] if out else [], strict=False):
            s1, s2 = side(cur), side(nxt)
            if s1 >= 0:
                clipped.append(cur)
            if (s1 >= 0) != (s2 >= 0):
                t = s1 / (s1 - s2)
                clipped.append((cur[0] + t * (nxt[0] - cur[0]), cur[1] + t * (nxt[1] - cur[1])))
        out = clipped
        if not out:
            break
    return out


def detect_contour(model: TerrainModel, mechanism: Mechanism, inp: pl.PlacementInput) -> Candidate:
    """Tillage across the slope: the part of the parcel with the slope in the band, rows at right angles to the fall.

    The band is the catalogue's (4-15%), a team proposal. NRCS Practice Standard 330 (Contour Farming) names 2-10%,
    and the two disagree at both ends. We keep the catalogue's lower end, since below 4% the heights (0.1 m) hardly
    tell the fall and rows are hard to keep level, and its upper end, because it is the row limit of our own source;
    above NRCS's 10% the candidate carries a risk line that says the practice alone no longer holds the water.
    The decision is made on the slope of the plane fitted to the parcel; the polygon is the cells whose own slope is
    in the band, as a convex hull clipped to the outline."""
    plane, why = _slope_check(model, inp)
    if plane is None:
        return _no_place(mechanism, why, slope_pct=model.slope_pct)
    lo = pl._cond("uprawa-w-poprzek-stoku", "slope_min_pct")
    hi = pl._cond("uprawa-w-poprzek-stoku", "slope_max_pct")
    if lo is None:
        return _no_place(mechanism, "katalog nie podaje przedziału spadku dla uprawy w poprzek stoku")
    band = f"{_num(lo, 0)}–{_num(hi, 0)}%" if hi is not None else f"od {_num(lo, 0)}%"
    outside = plane.slope_pct < lo or (hi is not None and plane.slope_pct > hi)
    cells = [] if outside else _band_cells(inp, lo, hi)
    polygon: list[tuple[float, float]] = []
    if len(cells) >= MIN_TILLAGE_CELLS and inp.grid is not None:
        half = inp.grid.step_m / 2.0
        corners = [(x + dx, y + dy) for x, y in cells for dx in (-half, half) for dy in (-half, half)]
        polygon = _clip_to_convex(inp.outline_2180, _hull(corners))
    if len(polygon) < 3:
        return _no_place(
            mechanism,
            f"spadek {pl._slope_text(plane.slope_pct)}% leży poza przedziałem {band}, w którym uprawa "
            "w poprzek stoku ma sens"
            if outside
            else f"w przedziale spadku {band} leży mniej niż {MIN_TILLAGE_CELLS} komórek działki",
            slope_pct=round(plane.slope_pct, 2),
        )
    azimuth = rows_azimuth(plane.downhill_deg)
    area_ha = round(len(cells) * inp.grid.step_m**2 / 10_000.0, 2) if inp.grid else None
    words = row_direction_words(azimuth)
    risks = ["na spadku powyżej górnego progu rzędy w poprzek stoku mogą się przerywać"]
    if plane.slope_pct > NRCS_CONTOUR_MAX_PCT:
        risks.append(
            f"spadek powyżej {_num(NRCS_CONTOUR_MAX_PCT, 0)}%: wg NRCS 330 sama uprawa w poprzek stoku "
            "nie wystarcza, potrzebne są jeszcze pasy lub miedze"
        )
    return Candidate(
        mechanism_id=mechanism.id,
        cause_codes=list(mechanism.causes_addressed),
        geometry=Geometry(
            type="polygon",
            coordinates=[(round(x, 1), round(y, 1)) for x, y in polygon],
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
        risks=risks,
        next_step=f"siej i orz rzędami {words}",
    )


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
