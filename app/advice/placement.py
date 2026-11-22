"""Where the retention actions go on a parcel: from the geometry of the parcel itself.

The base. A plane z = ax + by + c is fitted by least squares to the heights of the grid cells inside the parcel. Its
slope in percent and its downhill direction say where the water goes on average. The lower edge is the longest
continuous part of the outline whose heights lie in the lowest quarter of the outline's height range. Next to it we
take the lowest boundary point and the lowest interior point from the grid, the depressions (a cell lower than all
eight neighbours) and the nearest BDOT10k ditch. From these the rules follow: a grass strip on the lower edge (along
the ditch, when one runs by it), tillage across the slope, a basin in a depression or at the lowest interior point, a
weir only on a ditch by the lower edge. A plane too flat to show a lower edge gets a sentence instead.

The extension. D8 flow accumulation (O'Callaghan and Mark 1984) on a grid with a margin of about 300 m, and the wettest
points from the NDMI of dry periods. Each replaces the lowest point only when it scores higher than the base in the
ditch test (outlet) or the pond test (basin) in `metrics.json`; a tie keeps the base.

Only numpy: no dependency that fails to install on Windows, and the module can be replaced without touching the
report. Thresholds (smallest slope, ditch distance, depth of a depression) are read from `catalog_retencja.csv`
through `load_catalog()` at every call, not kept here.
"""

from __future__ import annotations

import importlib
import json
import math
from collections import deque
from dataclasses import dataclass, field
from heapq import heapify, heappop, heappush
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pyproj import Transformer

from app.advice import catalog as _catalog
from app.advice.catalog import CatalogRow
from app.geodata import ElevationGrid, WaterFeature
from app.models import Place

_TO_LONLAT = Transformer.from_crs("EPSG:2180", "EPSG:4326", always_xy=True)

# Share of the outline's height range (from its lowest point) that still counts as the lower edge. Team proposal:
# the lowest quarter; on a plane it gives the downhill side and the low ends of the two sides next to it.
LOWER_EDGE_FRACTION = 0.25

# Height added per cell when a flat is drained towards its spill point (metres). Team proposal: far below the
# 0.1 m rounding of the heights, and a 1000-cell flat still raises less than 1 mm.
FLAT_GRADIENT_M = 1e-6

# Upstream area from which a cell counts as concentrated flow (a flow line on the map). Team proposal: 1 ha.
FLOW_LINE_MIN_HA = 1.0

# Spacing of the points used to measure distances to ditches and ponds (metres). A sampling step, not a threshold.
POINT_SPACING_M = 5.0

# Where `make eval` writes the scores of the outlet and basin variants (read from the working directory).
METRICS_PATH = Path("metrics.json")

Variant = Literal["lowest", "d8", "ndmi"]
_VARIANTS: tuple[Variant, ...] = ("lowest", "d8", "ndmi")  # the order is the tie-break

# (row step, column step) of E, NE, N, NW, W, SW, S, SE.
_OFFS = ((0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1), (1, 0), (1, 1))


def load_catalog() -> dict[str, CatalogRow]:
    """The action catalogue, looked up at call time so a replaced reader or row is honoured."""
    return _catalog.load_catalog()


def _cond(action_id: str, name: str) -> float | None:
    row = load_catalog().get(action_id)
    return row.cond(name) if row else None


# --------------------------------------------------------------------------------------------------------------
# Types
# --------------------------------------------------------------------------------------------------------------


@dataclass
class PlacementInput:
    outline_2180: list[list[float]]  # outer ring, [x, y] in EPSG:2180
    grid: ElevationGrid | None
    lowest_outline_point_2180: list[float] | None
    water: list[WaterFeature] = field(default_factory=list)
    slope_mean_pct: float | None = None
    wet: Any = None  # app.advice.wet_zones.WetZones, when the report has computed it (variant "ndmi")


@dataclass
class Plane:
    """z = a * x + b * y + c (x east, y north, metres), fitted to the cells inside the parcel."""

    a: float
    b: float
    c: float
    slope_pct: float  # 100 * sqrt(a^2 + b^2)
    downhill_deg: float  # azimuth of the vector (-a, -b): 0 north, 90 east, 180 south, 270 west


@dataclass
class LowerEdge:
    points_2180: list[list[float]]  # a continuous part of the outline, a point every grid step
    length_m: float
    middle_2180: list[float]  # the point halfway along it


@dataclass
class BoundaryPoint:
    x_2180: float
    y_2180: float
    catchment_ha: float  # water that crosses the boundary here, from upstream cells


@dataclass
class Runoff:
    outlets: list[BoundaryPoint] = field(default_factory=list)  # water leaves the parcel, largest first
    inlets: list[BoundaryPoint] = field(default_factory=list)  # water enters from neighbours, largest first
    flow_lines: list[list[list[float]]] = field(default_factory=list)  # [[x, y], ...] in EPSG:2180
    reason: str = ""  # why there are no flow lines ("spadek 0,3% jest za mały, by wskazać linię spływu")


@dataclass
class PlaceCandidate:
    kind: (
        str  # "punkt wypływu", "pas trawy", "uprawa w poprzek stoku", "niecka", "zastawka", "rów", "zbiornik"
    )
    place: Place | None
    reason: str = ""  # why there is no place ("spadek 0,3% jest za mały, by wskazać dolny odcinek granicy")
    catchment_ha: float | None = None  # water this action intercepts (variant "d8" only)
    length_m: float | None = None  # grass strip: length of the lower edge
    direction_deg: float | None = None  # tillage: azimuth in [0, 180) of ploughing and sowing
    slope_pct: float | None = None  # slope of the fitted plane
    distance_m: float | None = None  # ditch or pond to the lower edge or the parcel

    @property
    def no_place_reason(self) -> str:
        return f"brak miejsca na działce, bo {self.reason}" if self.reason else ""


# --------------------------------------------------------------------------------------------------------------
# Grid access
# --------------------------------------------------------------------------------------------------------------


def _heights(grid: ElevationGrid) -> np.ndarray:
    """Heights as a float array, nan where unknown."""
    return np.array(grid.z, dtype=float).reshape(grid.rows, grid.cols)


def _inside(grid: ElevationGrid) -> np.ndarray:
    return np.array(grid.inside, dtype=bool).reshape(grid.rows, grid.cols)


def _centres(grid: ElevationGrid, rows: np.ndarray, cols: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    return grid.x0 + (cols + 0.5) * grid.step_m, grid.y_top - (rows + 0.5) * grid.step_m


def _sample(grid: ElevationGrid, z: np.ndarray, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    """Bilinear height at the points; unknown corners are left out of the weights; nan when all four are unknown."""
    fc = (xs - grid.x0) / grid.step_m - 0.5
    fr = (grid.y_top - ys) / grid.step_m - 0.5
    c0, r0 = np.floor(fc).astype(int), np.floor(fr).astype(int)
    tc, tr = fc - c0, fr - r0
    total = np.zeros(len(xs))
    weight = np.zeros(len(xs))
    for dr, wr in ((0, 1.0 - tr), (1, tr)):
        for dc, wc in ((0, 1.0 - tc), (1, tc)):
            v = z[np.clip(r0 + dr, 0, grid.rows - 1), np.clip(c0 + dc, 0, grid.cols - 1)]
            w = wr * wc * np.isfinite(v)
            total += w * np.nan_to_num(v)
            weight += w
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(weight > 1e-9, total / weight, np.nan)


def _dense(ring: list[list[float]], spacing: float) -> np.ndarray:
    """Points along a line every `spacing` metres, vertices included."""
    pts: list[tuple[float, float]] = []
    for (x1, y1), (x2, y2) in zip(ring, ring[1:], strict=False):
        n = max(1, int(math.ceil(math.hypot(x2 - x1, y2 - y1) / spacing)))
        pts += [(x1 + (x2 - x1) * k / n, y1 + (y2 - y1) * k / n) for k in range(n)]
    pts.append((ring[-1][0], ring[-1][1]))
    return np.array(pts)


def _outline_points(inp: PlacementInput, spacing: float) -> np.ndarray:
    """Points of the closed outline every `spacing` metres, the closing point not repeated."""
    pts = _dense(inp.outline_2180, spacing)
    if len(pts) > 1 and np.allclose(pts[0], pts[-1]):
        pts = pts[:-1]
    return pts


def _central(points: np.ndarray) -> int:
    """Index of the point nearest to the mean of the points: a tie of equally low points resolves to their middle."""
    return int(np.hypot(*(points - points.mean(axis=0)).T).argmin())


def _round_point(x: float, y: float) -> list[float]:
    return [round(float(x), 1), round(float(y), 1)]


# --------------------------------------------------------------------------------------------------------------
# The base: plane, lower edge, lowest points, depressions
# --------------------------------------------------------------------------------------------------------------


def fit_plane(grid: ElevationGrid) -> Plane:
    """Least-squares plane through the cell centres inside the parcel; ValueError when too few have heights."""
    z, inside = _heights(grid), _inside(grid)
    rows, cols = np.nonzero(inside & np.isfinite(z))
    if len(rows) < 3:
        raise ValueError("fewer than three cells with heights inside the parcel")
    xs, ys = _centres(grid, rows, cols)
    cx, cy = float(xs.mean()), float(ys.mean())  # centred coordinates keep the fit well conditioned
    design = np.column_stack([xs - cx, ys - cy, np.ones(len(xs))])
    (a, b, c0), *_ = np.linalg.lstsq(design, z[rows, cols], rcond=None)
    a, b = float(a), float(b)
    return Plane(
        a=a,
        b=b,
        c=float(c0) - a * cx - b * cy,
        slope_pct=100.0 * math.hypot(a, b),
        downhill_deg=math.degrees(math.atan2(-a, -b)) % 360.0,
    )


def _lower_edge(inp: PlacementInput, plane: Plane) -> LowerEdge | None:
    minimum = _cond("pas-trawy-przy-wyplywie", "slope_min_pct")
    if inp.grid is None or minimum is None or plane.slope_pct < minimum:
        return None
    step = inp.grid.step_m
    pts = _outline_points(inp, step)
    h = _sample(inp.grid, _heights(inp.grid), pts[:, 0], pts[:, 1])
    if len(pts) < 3 or not np.isfinite(h).any():
        return None
    lo, hi = float(np.nanmin(h)), float(np.nanmax(h))
    if hi - lo <= 0.0:
        return None
    # start at the highest point so that no low part wraps around the start of the list
    order = (int(np.nanargmax(h)) + np.arange(len(pts))) % len(pts)
    low = np.nan_to_num(h[order], nan=np.inf) <= lo + LOWER_EDGE_FRACTION * (hi - lo)
    best: tuple[int, int] = (0, 0)  # (start, length) of the longest run of low points
    start = 0
    for i in range(len(low) + 1):
        if i == len(low) or not low[i]:
            if i - start > best[1]:
                best = (start, i - start)
            start = i + 1
    if best[1] == 0:
        return None
    run = pts[order[best[0] : best[0] + best[1]]]
    gaps = np.hypot(*np.diff(run, axis=0).T) if len(run) > 1 else np.array([])
    length = float(gaps.sum()) if len(gaps) else float(step)
    reached = np.concatenate([[0.0], np.cumsum(gaps)])
    k = int(np.searchsorted(reached, length / 2.0))
    k = min(k, len(run) - 1)
    mid = run[k]
    return LowerEdge([_round_point(x, y) for x, y in run], round(length, 1), _round_point(*mid))


def lower_edge(inp: PlacementInput) -> LowerEdge | None:
    """The longest continuous part of the outline in the lowest quarter of its heights.

    None when the plane falls less than the smallest slope of the catalogue row "pas-trawy-przy-wyplywie", or the grid
    has no heights.
    """
    if inp.grid is None:
        return None
    try:
        plane = fit_plane(inp.grid)
    except ValueError:
        return None
    return _lower_edge(inp, plane)


def lowest_boundary_point(inp: PlacementInput) -> list[float] | None:
    """The lowest point of the outline, with heights from the grid; the middle of a tie of equal heights."""
    if inp.grid is None:
        return None
    pts = _outline_points(inp, inp.grid.step_m)
    h = _sample(inp.grid, _heights(inp.grid), pts[:, 0], pts[:, 1])
    if not np.isfinite(h).any():
        return None
    if np.nanmax(h) - np.nanmin(h) <= 1e-9:
        return None  # equal heights all along the outline: no lowest point to name
    tied = pts[h <= np.nanmin(h) + 1e-9]
    x, y = tied[_central(tied)]
    return _round_point(x, y)


def lowest_interior_point(inp: PlacementInput) -> list[float] | None:
    """The centre of the lowest cell inside the parcel; the middle of a tie of equal heights."""
    if inp.grid is None:
        return None
    z, inside = _heights(inp.grid), _inside(inp.grid)
    rows, cols = np.nonzero(inside & np.isfinite(z))
    if not len(rows):
        return None
    h = z[rows, cols]
    if h.max() - h.min() <= 1e-9:
        return None  # equal heights everywhere inside: no lowest point to name
    tied = h <= h.min() + 1e-9
    xs, ys = _centres(inp.grid, rows[tied], cols[tied])
    pts = np.column_stack([xs, ys])
    x, y = pts[_central(pts)]
    return _round_point(x, y)


def _depression_cells(grid: ElevationGrid) -> list[tuple[float, float, float]]:
    """(x, y, depth) of the cells inside the parcel lower than all eight neighbours; depth below the lowest neighbour."""
    z, inside = _heights(grid), _inside(grid)
    if grid.rows < 3 or grid.cols < 3:
        return []
    neighbours = np.stack([_shifted(z, dr, dc, np.nan) for dr, dc in _OFFS])
    known = np.isfinite(neighbours).all(axis=0)  # a cell with an unknown neighbour is not called a depression
    lowest = np.where(known, neighbours.min(axis=0), np.nan)
    with np.errstate(invalid="ignore"):
        pit = inside & known & (z < lowest)
    rows, cols = np.nonzero(pit)
    xs, ys = _centres(grid, rows, cols)
    return [
        (float(x), float(y), float(lowest[r, c] - z[r, c]))
        for x, y, r, c in zip(xs, ys, rows, cols, strict=True)
    ]


def depressions(grid: ElevationGrid) -> list[list[float]]:
    """[x, y] of the cell centres inside the parcel that are lower than all eight neighbours."""
    return [_round_point(x, y) for x, y, _ in _depression_cells(grid)]


# --------------------------------------------------------------------------------------------------------------
# The extension: the variant that wins the tests in metrics.json
# --------------------------------------------------------------------------------------------------------------


def _winner(prefix: str) -> Variant:
    """The variant with the highest score under `retention.<prefix>_<variant>`; a tie keeps the base, then D8."""
    try:
        data = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "lowest"
    section = data.get("retention") if isinstance(data, dict) else None
    section = section if isinstance(section, dict) else {}
    scores: dict[str, float] = {}
    for name in _VARIANTS:
        value = section.get(f"{prefix}_{name}")
        if isinstance(value, int | float) and not isinstance(value, bool):
            scores[name] = float(value)
    if "lowest" not in scores:  # without the base score nothing can be said to beat it
        return "lowest"
    best = max(scores.values())
    return next(name for name in _VARIANTS if scores.get(name) == best)


def outlet_method() -> Variant:
    """ "lowest" | "d8" | "ndmi": the variant with the highest `retention.outlet_hit_*` in metrics.json."""
    return _winner("outlet_hit")


def basin_method() -> Variant:
    """ "lowest" | "d8" | "ndmi": the variant with the highest `retention.pond_auc_*` in metrics.json."""
    return _winner("pond_auc")


def _wet_points(inp: PlacementInput) -> tuple[list[float] | None, list[float] | None]:
    """Wettest boundary and interior point from the NDMI module; (None, None) when it is not there or has no result."""
    try:
        importlib.import_module("app.advice.wet_zones")
    except ImportError:
        return None, None
    wet = inp.wet
    if wet is None:
        return None, None
    boundary = getattr(wet, "wettest_boundary_2180", None)
    interior = getattr(wet, "wettest_interior_2180", None)
    return (
        [float(boundary[0]), float(boundary[1])] if boundary else None,
        [float(interior[0]), float(interior[1])] if interior else None,
    )


# --------------------------------------------------------------------------------------------------------------
# D8 flow accumulation (O'Callaghan and Mark 1984)
# --------------------------------------------------------------------------------------------------------------


def _flood(z: np.ndarray, seeds: list[int], gradient: float) -> np.ndarray:
    """Priority flood from the seed cells; every other cell ends at max(own height, lowest path out + gradient)."""
    rows, cols = z.shape
    flat = z.ravel().tolist()
    out = flat[:]
    closed = bytearray(len(flat))
    heap = []
    for i in seeds:
        if not closed[i]:
            closed[i] = 1
            heap.append((flat[i], i))
    heapify(heap)
    while heap:
        h, i = heappop(heap)
        r, c = divmod(i, cols)
        for dr, dc in _OFFS:
            rr, cc = r + dr, c + dc
            if 0 <= rr < rows and 0 <= cc < cols:
                j = rr * cols + cc
                if not closed[j]:
                    closed[j] = 1
                    v = flat[j]
                    floor = h + gradient
                    if v < floor:
                        v = floor
                    out[j] = v
                    heappush(heap, (v, j))
    return np.array(out, dtype=float).reshape(rows, cols)


def _edge_cells(rows: int, cols: int) -> list[int]:
    cells = {c for c in range(cols)} | {(rows - 1) * cols + c for c in range(cols)}
    cells |= {r * cols for r in range(rows)} | {r * cols + cols - 1 for r in range(rows)}
    return sorted(cells)


def _shifted(a: np.ndarray, dr: int, dc: int, fill: float) -> np.ndarray:
    """Value of the neighbour at (row + dr, col + dc) for every cell; `fill` beyond the grid."""
    rows, cols = a.shape
    out = np.full(a.shape, fill, dtype=float)
    r_src = slice(max(dr, 0), rows + min(dr, 0))
    r_dst = slice(max(-dr, 0), rows + min(-dr, 0))
    c_src = slice(max(dc, 0), cols + min(dc, 0))
    c_dst = slice(max(-dc, 0), cols + min(-dc, 0))
    out[r_dst, c_dst] = a[r_src, c_src]
    return out


@dataclass
class _Flow:
    """Where each cell sends its water (one receiver, D8) and the upstream area."""

    to: np.ndarray  # flat index of the receiver or -1
    acc_ha: np.ndarray  # upstream area including the cell itself, ha


@dataclass
class _Surface:
    grid: ElevationGrid
    rows: int
    cols: int
    step: float
    drained: (
        np.ndarray
    )  # depressions filled by priority flood, flats drained: strictly lower along every flow path
    inside: np.ndarray  # bool
    flow: _Flow

    def centre(self, r: float, c: float) -> tuple[float, float]:
        return self.grid.x0 + (c + 0.5) * self.step, self.grid.y_top - (r + 0.5) * self.step

    def xy(self, idx: int) -> tuple[float, float]:
        r, c = divmod(int(idx), self.cols)
        return self.centre(r, c)


def _build_surface(grid: ElevationGrid) -> _Surface:
    rows, cols = grid.rows, grid.cols
    raw = _heights(grid)
    unknown = np.isnan(raw)
    if unknown.all():
        raise ValueError("elevation grid without heights")
    z = np.where(
        unknown, np.nanmin(raw) - 1.0, raw
    )  # water that reaches a cell without height leaves the grid
    seeds = sorted(set(_edge_cells(rows, cols)) | set(np.flatnonzero(unknown.ravel()).tolist()))
    drained = _flood(z, seeds, FLAT_GRADIENT_M)
    surface = _Surface(
        grid, rows, cols, float(grid.step_m), drained, _inside(grid), _Flow(np.empty(0), np.empty(0))
    )
    surface.flow = _d8(surface)
    return surface


def _d8(s: _Surface) -> _Flow:
    """Each cell drains to its steepest lower neighbour; ties go to the first of E, NE, N, ... (deterministic)."""
    w = s.drained
    dist = [s.step if (dr == 0 or dc == 0) else s.step * math.sqrt(2.0) for dr, dc in _OFFS]
    nb = [_shifted(w, dr, dc, float(w.max()) + 1e6) for dr, dc in _OFFS]  # beyond the grid: far above
    idx = np.arange(s.rows * s.cols).reshape(s.rows, s.cols)
    off_idx = np.array([dr * s.cols + dc for dr, dc in _OFFS])
    edge = np.zeros((s.rows, s.cols), dtype=bool)
    edge[0, :] = edge[-1, :] = edge[:, 0] = edge[:, -1] = True
    drop = np.stack([(w - n) / d for n, d in zip(nb, dist, strict=True)])
    best = drop.argmax(axis=0)
    ok = (np.take_along_axis(drop, best[None], axis=0)[0] > 0) & ~edge
    to = np.where(ok, idx + off_idx[best], -1).ravel()
    return _Flow(to, _accumulate(s, to))


def _accumulate(s: _Surface, to: np.ndarray) -> np.ndarray:
    """Upstream area in ha: cells from the highest to the lowest pass their water on."""
    acc = np.full(s.rows * s.cols, s.step * s.step / 10_000.0)
    for i in np.argsort(-s.drained.ravel(), kind="stable").tolist():
        j = to[i]
        if j >= 0:
            acc[j] += acc[i]
    return acc


def _segment_hit(
    p: tuple[float, float], q: tuple[float, float], ring: list[list[float]]
) -> tuple[float, float]:
    """Where the segment p-q crosses the ring; the midpoint when it does not."""
    best_t = None
    px, py = p
    rx, ry = q[0] - px, q[1] - py
    for (x1, y1), (x2, y2) in zip(ring, ring[1:], strict=False):
        sx, sy = x2 - x1, y2 - y1
        den = rx * sy - ry * sx
        if den == 0:
            continue
        t = ((x1 - px) * sy - (y1 - py) * sx) / den
        u = ((x1 - px) * ry - (y1 - py) * rx) / den
        if 0 <= t <= 1 and 0 <= u <= 1 and (best_t is None or t < best_t):
            best_t = t
    t = 0.5 if best_t is None else best_t
    return px + t * rx, py + t * ry


def _clusters(cells: list[int], cols: int) -> list[list[int]]:
    """Group 8-adjacent cells (positions in `cells`) so one outlet with a split flow stays one outlet."""
    where = {cell: k for k, cell in enumerate(cells)}
    seen: set[int] = set()
    groups: list[list[int]] = []
    for k, cell in enumerate(cells):
        if k in seen:
            continue
        seen.add(k)
        group, queue = [k], deque([cell])
        while queue:
            r, c = divmod(queue.popleft(), cols)
            for dr, dc in _OFFS:
                nxt = where.get((r + dr) * cols + c + dc)
                if nxt is not None and nxt not in seen and 0 <= c + dc < cols:
                    seen.add(nxt)
                    group.append(nxt)
                    queue.append(cells[nxt])
        groups.append(group)
    return groups


@dataclass
class _Crossing:
    point: BoundaryPoint
    inside_cell: int  # the cell of the pair that lies inside the parcel


def _crossings(s: _Surface, ring: list[list[float]], leaving: bool) -> list[_Crossing]:
    """Flow across the parcel boundary, in ha, one entry per group of adjacent crossing cells, largest first."""
    inside = s.inside.ravel()
    to = s.flow.to
    src = np.flatnonzero(to >= 0)
    dst = to[src]
    across = (inside[src] & ~inside[dst]) if leaving else (~inside[src] & inside[dst])
    edges = sorted(
        (
            (float(s.flow.acc_ha[a]), a, b)
            for a, b in zip(src[across].tolist(), dst[across].tolist(), strict=True)
        ),
        key=lambda e: -e[0],
    )
    if not edges:
        return []
    # the cell on the parcel's side of the boundary identifies a crossing
    side = [(e[1] if leaving else e[2]) for e in edges]
    cells = list(dict.fromkeys(side))
    out: list[_Crossing] = []
    for group in _clusters(cells, s.cols):
        members = {cells[k] for k in group}
        mine = [e for e, cell in zip(edges, side, strict=True) if cell in members]
        _, a, b = mine[0]  # the largest flow of the group places the point
        x, y = _segment_hit(s.xy(a), s.xy(b), ring)
        total = sum(e[0] for e in mine)
        out.append(_Crossing(BoundaryPoint(round(x, 1), round(y, 1), round(total, 2)), a if leaving else b))
    out.sort(key=lambda c: -c.point.catchment_ha)
    return out


def _flow_lines(s: _Surface) -> list[list[list[float]]]:
    """Polylines through the cells above the area threshold, head to mouth."""
    flow = s.flow
    on = flow.acc_ha >= FLOW_LINE_MIN_HA
    if not on.any():
        return []
    has_upstream = np.zeros(on.shape, dtype=bool)
    src = np.flatnonzero(on & (flow.to >= 0))
    has_upstream[flow.to[src]] = True
    visited = np.zeros(on.shape, dtype=bool)
    lines: list[list[list[float]]] = []
    for head in np.flatnonzero(on & ~has_upstream).tolist():
        line: list[list[float]] = []
        i = head
        while True:
            x, y = s.xy(i)
            line.append([round(x, 1), round(y, 1)])
            if visited[i]:
                break  # joined a line that is already drawn
            visited[i] = True
            nxt = int(flow.to[i])
            if nxt < 0 or not on[nxt]:
                break
            i = nxt
        if len(line) > 1:
            lines.append(line)
    return lines


def _slope_text(slope_pct: float) -> str:
    """One decimal, two when one decimal would read as the catalogue's minimum although the slope is below it."""
    minimum = _cond("pas-trawy-przy-wyplywie", "slope_min_pct")
    two = minimum is not None and slope_pct < minimum <= round(slope_pct, 1)
    return f"{slope_pct:.2f}".replace(".", ",") if two else f"{slope_pct:.1f}".replace(".", ",")


def _too_flat(plane: Plane) -> bool:
    minimum = _cond("pas-trawy-przy-wyplywie", "slope_min_pct")
    return minimum is None or plane.slope_pct < minimum


def runoff(inp: PlacementInput) -> Runoff:
    """Outlets, inlets and flow lines of the parcel by D8; `reason` instead of lines when the slope is too small.

    The grid should reach about 300 m beyond the parcel, otherwise the catchments of the inlets are cut off.
    """
    if inp.grid is None:
        return Runoff(reason="brak siatki wysokości dla działki")
    try:
        plane = fit_plane(inp.grid)
        surface = _build_surface(inp.grid)
    except ValueError:
        return Runoff(reason="brak wysokości w siatce dla działki")
    if _too_flat(plane):
        return Runoff(reason=f"spadek {_slope_text(plane.slope_pct)}% jest za mały, by wskazać linię spływu")
    ring = inp.outline_2180
    return Runoff(
        outlets=[c.point for c in _crossings(surface, ring, leaving=True)],
        inlets=[c.point for c in _crossings(surface, ring, leaving=False)],
        flow_lines=_flow_lines(surface),
    )


# --------------------------------------------------------------------------------------------------------------
# Words for places
# --------------------------------------------------------------------------------------------------------------

_COMPASS = {
    (-1, 1): "północno-zachodnim narożniku",
    (0, 1): "północnej części działki",
    (1, 1): "północno-wschodnim narożniku",
    (-1, 0): "zachodniej części działki",
    (0, 0): "środkowej części działki",
    (1, 0): "wschodniej części działki",
    (-1, -1): "południowo-zachodnim narożniku",
    (0, -1): "południowej części działki",
    (1, -1): "południowo-wschodnim narożniku",
}

_SIDES = (
    "północnej",
    "północno-wschodniej",
    "wschodniej",
    "południowo-wschodniej",
    "południowej",
    "południowo-zachodniej",
    "zachodniej",
    "północno-zachodniej",
)


def _bbox(ring: list[list[float]]) -> tuple[float, float, float, float]:
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    return min(xs), min(ys), max(xs), max(ys)


def _where(x: float, y: float, ring: list[list[float]]) -> str:
    """The part of the parcel (a 3 x 3 split of its bounding box) a point lies in, in the locative."""
    x0, y0, x1, y1 = _bbox(ring)
    u = (x - x0) / max(x1 - x0, 1e-9)
    v = (y - y0) / max(y1 - y0, 1e-9)
    col = -1 if u < 1 / 3 else (1 if u > 2 / 3 else 0)
    row = -1 if v < 1 / 3 else (1 if v > 2 / 3 else 0)
    return _COMPASS[(col, row)]


def _side(x: float, y: float, ring: list[list[float]]) -> str:
    """The side of the parcel a boundary point lies on, in the genitive/locative ("zachodniej")."""
    x0, y0, x1, y1 = _bbox(ring)
    azimuth = math.degrees(math.atan2(x - (x0 + x1) / 2, y - (y0 + y1) / 2)) % 360.0
    return _SIDES[int(round(azimuth / 45.0)) % 8]


def _place(
    kind: str,
    x: float,
    y: float,
    description: str,
    catchment_ha: float | None = None,
    length_m: float | None = None,
    direction_deg: float | None = None,
) -> Place:
    lon, lat = _TO_LONLAT.transform(x, y)
    return Place(
        kind=kind,
        x_2180=round(x, 1),
        y_2180=round(y, 1),
        lon=lon,
        lat=lat,
        description=description,
        catchment_ha=None if catchment_ha is None else round(catchment_ha, 2),
        length_m=None if length_m is None else round(length_m, 1),
        direction_deg=None if direction_deg is None else round(direction_deg, 1),
    )


# --------------------------------------------------------------------------------------------------------------
# Water from BDOT10k
# --------------------------------------------------------------------------------------------------------------


def _water_points(feature: WaterFeature) -> np.ndarray:
    pts = [_dense(ring, POINT_SPACING_M) for ring in feature.rings_2180 if len(ring) > 1]
    return np.vstack(pts) if pts else np.empty((0, 2))


def _ditch_by_edge(inp: PlacementInput, edge: LowerEdge, max_m: float) -> tuple[list[float], float] | None:
    """The ditch point nearest to the lower edge within `max_m`, and its distance; the one nearest the edge's middle
    among equally near points."""
    edge_pts = (
        _dense(edge.points_2180, POINT_SPACING_M) if len(edge.points_2180) > 1 else np.array(edge.points_2180)
    )
    best: tuple[float, np.ndarray] | None = None
    for feature in inp.water:
        if feature.kind != "ditch":
            continue
        pts = _water_points(feature)
        if not len(pts):
            continue
        d = np.hypot(pts[:, None, 0] - edge_pts[None, :, 0], pts[:, None, 1] - edge_pts[None, :, 1]).min(
            axis=1
        )
        near = pts[d <= d.min() + POINT_SPACING_M / 2.0]
        mid = np.array(edge.middle_2180)
        point = near[int(np.hypot(*(near - mid).T).argmin())]
        if best is None or d.min() < best[0]:
            best = (float(d.min()), point)
    if best is None or best[0] > max_m:
        return None
    return _round_point(*best[1]), round(best[0], 1)


def _water_candidates(inp: PlacementInput, edge: LowerEdge | None) -> list[PlaceCandidate]:
    """The ditch to rebuild and the pond to protect, both from BDOT10k and the distance rules of the catalogue."""
    out: list[PlaceCandidate] = []
    ring = inp.outline_2180
    x0, y0, x1, y1 = _bbox(ring)
    centre = np.array([(x0 + x1) / 2, (y0 + y1) / 2])
    ref = np.array(edge.middle_2180) if edge else centre
    rebuild_max = _cond("przebudowa-rowu", "ditch_max_m")
    pond_max = _cond("ochrona-zbiornika", "ditch_max_m")
    ditch_seen = False
    for feature in inp.water:
        pts = _water_points(feature)
        if not len(pts):
            continue
        if (
            feature.kind == "ditch"
            and not ditch_seen
            and rebuild_max is not None
            and feature.distance_m <= rebuild_max
        ):
            ditch_seen = True
            hx, hy = pts[int(np.hypot(*(pts - ref).T).argmin())]
            out.append(
                PlaceCandidate(
                    kind="rów",
                    place=_place("rów", hx, hy, f"rowie przy {_where(hx, hy, ring)}"),
                    distance_m=round(feature.distance_m, 1),
                )
            )
        elif feature.kind == "water_body" and pond_max is not None and feature.distance_m <= pond_max:
            hx, hy = pts[int(np.hypot(*(pts - centre).T).argmin())]
            out.append(
                PlaceCandidate(
                    kind="zbiornik",
                    place=_place("zbiornik", hx, hy, f"zbiorniku przy {_where(hx, hy, ring)}"),
                    distance_m=round(feature.distance_m, 1),
                )
            )
    return out


# --------------------------------------------------------------------------------------------------------------
# Places
# --------------------------------------------------------------------------------------------------------------


def _without_grid(inp: PlacementInput, reason: str) -> list[PlaceCandidate]:
    """No heights: the outlet only from a lowest outline point given by the caller, water from BDOT10k."""
    if inp.lowest_outline_point_2180 is None:
        outlet = PlaceCandidate(kind="punkt wypływu", place=None, reason=reason)
    else:
        x, y = inp.lowest_outline_point_2180
        outlet = PlaceCandidate(
            kind="punkt wypływu", place=_place("punkt wypływu", x, y, "najniższy punkt granicy")
        )
    return [outlet, *_water_candidates(inp, None)]


def _interior_cell_near_centre(inp: PlacementInput) -> tuple[float, float] | None:
    """The centre of the cell inside the parcel nearest to the mean of the inside cells."""
    assert inp.grid is not None
    rows, cols = np.nonzero(_inside(inp.grid))
    if not len(rows):
        return None
    xs, ys = _centres(inp.grid, rows, cols)
    pts = np.column_stack([xs, ys])
    x, y = pts[_central(pts)]
    return float(x), float(y)


@dataclass
class _Context:
    """What every place function of `find_places` reads: the input, the fitted plane and the winning variants."""

    inp: PlacementInput
    plane: Plane
    flat: bool
    slope_text: str
    edge: LowerEdge | None
    outlet_variant: Variant
    basin_variant: Variant
    crossing: _Crossing | None
    wet_boundary: list[float] | None
    wet_interior: list[float] | None

    @property
    def grid(self) -> ElevationGrid:
        assert self.inp.grid is not None
        return self.inp.grid

    @property
    def ring(self) -> list[list[float]]:
        return self.inp.outline_2180


def _outlet_place(c: _Context) -> PlaceCandidate:
    """The lowest boundary point, or the point of the winning variant."""
    outlet_ha: float | None = None
    text = "najniższy punkt granicy"
    if c.outlet_variant == "d8" and c.crossing is not None:
        outlet_xy: list[float] | None = [c.crossing.point.x_2180, c.crossing.point.y_2180]
        outlet_ha = c.crossing.point.catchment_ha
        text = "punkt, którędy z działki wypływa najwięcej wody"
    elif c.outlet_variant == "ndmi" and c.wet_boundary is not None:
        outlet_xy, text = c.wet_boundary, "najwilgotniejszy punkt granicy"
    else:
        outlet_xy = lowest_boundary_point(c.inp)
    if outlet_xy is None:
        why = (
            f"spadek {c.slope_text}% jest za mały, by wskazać punkt wypływu"
            if c.flat
            else "brak wysokości wzdłuż granicy działki"
        )
        return PlaceCandidate(kind="punkt wypływu", place=None, reason=why)
    x, y = outlet_xy
    return PlaceCandidate(
        kind="punkt wypływu",
        place=_place("punkt wypływu", x, y, f"{text}, w {_where(x, y, c.ring)}", outlet_ha),
        catchment_ha=outlet_ha,
    )


def _strip_place(c: _Context, outlet_ha: float | None) -> PlaceCandidate:
    """The grass strip on the lower edge, along the ditch when one runs by it."""
    if c.flat:
        return PlaceCandidate(
            kind="pas trawy",
            place=None,
            reason=f"spadek {c.slope_text}% jest za mały, by wskazać dolny odcinek granicy",
            slope_pct=round(c.plane.slope_pct, 2),
        )
    if c.edge is None:
        return PlaceCandidate(kind="pas trawy", place=None, reason="brak wysokości wzdłuż granicy działki")
    ditch_max = _cond("pas-trawy-przy-wyplywie", "ditch_max_m")
    mx, my = c.edge.middle_2180
    along = ditch_max is not None and _ditch_by_edge(c.inp, c.edge, ditch_max) is not None
    side = f"na {_side(mx, my, c.ring)} granicy"
    return PlaceCandidate(
        kind="pas trawy",
        place=_place(
            "pas trawy",
            mx,
            my,
            f"wzdłuż rowu {side}" if along else side,
            outlet_ha,
            length_m=c.edge.length_m,
        ),
        catchment_ha=outlet_ha,
        length_m=c.edge.length_m,
        slope_pct=round(c.plane.slope_pct, 2),
    )


def _basin_place(c: _Context) -> PlaceCandidate:
    """In a depression when there is one, else at the lowest interior point."""
    depth_min = _cond("niecka-przy-wyplywie", "depression_min_m")
    pits = [p for p in _depression_cells(c.grid) if depth_min is not None and p[2] >= depth_min - 1e-9]
    basin_xy: list[float] | None
    basin_ha: float | None = None
    if pits:
        x, y, _ = max(pits, key=lambda p: p[2])
        basin_xy, basin_text = [x, y], "zagłębieniu terenu"
    elif c.basin_variant == "ndmi" and c.wet_interior is not None:
        basin_xy, basin_text = c.wet_interior, "najwilgotniejszym miejscu wnętrza"
    elif c.basin_variant == "d8" and c.crossing is not None:
        basin_xy = list(_build_surface(c.grid).xy(c.crossing.inside_cell))
        basin_text, basin_ha = "miejscu, do którego spływa najwięcej wody", c.crossing.point.catchment_ha
    else:
        basin_xy, basin_text = lowest_interior_point(c.inp), "najniższym punkcie wnętrza"
    if basin_xy is None:
        why = (
            f"spadek {c.slope_text}% jest za mały, by wskazać nieckę, a w siatce nie ma zagłębienia"
            if c.flat
            else "brak wysokości wewnątrz działki"
        )
        return PlaceCandidate(kind="niecka", place=None, reason=why)
    x, y = basin_xy
    return PlaceCandidate(
        kind="niecka",
        place=_place("niecka", x, y, f"{basin_text}, w {_where(x, y, c.ring)}", basin_ha),
        catchment_ha=basin_ha,
    )


def _tillage_place(c: _Context) -> PlaceCandidate | None:
    """Tillage across the slope, only inside the slope band of the catalogue."""
    lo, hi = (
        _cond("uprawa-w-poprzek-stoku", "slope_min_pct"),
        _cond("uprawa-w-poprzek-stoku", "slope_max_pct"),
    )
    centre = _interior_cell_near_centre(c.inp)
    if lo is None or c.plane.slope_pct < lo or (hi is not None and c.plane.slope_pct > hi) or not centre:
        return None
    direction = round((c.plane.downhill_deg + 90.0) % 180.0, 1) % 180.0  # rounding must not reach 180
    return PlaceCandidate(
        kind="uprawa w poprzek stoku",
        place=_place(
            "uprawa w poprzek stoku", centre[0], centre[1], "całej działce", direction_deg=direction
        ),
        direction_deg=round(direction, 1),
        slope_pct=round(c.plane.slope_pct, 2),
    )


def _weir_place(c: _Context, outlet_ha: float | None) -> PlaceCandidate | None:
    """A weir only on a ditch by the lower edge."""
    weir_max = _cond("zastawka-nowa", "ditch_max_m")
    if c.edge is None or weir_max is None:
        return None
    hit = _ditch_by_edge(c.inp, c.edge, weir_max)
    if hit is None:
        return None
    (hx, hy), dist = hit
    return PlaceCandidate(
        kind="zastawka",
        place=_place("zastawka", hx, hy, f"rowie przy {_where(hx, hy, c.ring)}", outlet_ha),
        catchment_ha=outlet_ha,
        distance_m=dist,
    )


def find_places(inp: PlacementInput) -> list[PlaceCandidate]:
    """Candidate places for retention actions: with a place, or with the reason there is none.

    "punkt wypływu" is always present. A grass strip needs a lower edge: when the plane is too flat the candidate has
    no place and its reason says so. Thresholds come from the catalogue.
    """
    if inp.grid is None:
        return _without_grid(inp, "brak siatki wysokości dla działki")
    try:
        plane = fit_plane(inp.grid)
    except ValueError:
        return _without_grid(inp, "brak wysokości w siatce dla działki")

    flat = _too_flat(plane)
    outlet_variant, basin_variant = outlet_method(), basin_method()
    crossing: _Crossing | None = None
    if "d8" in (outlet_variant, basin_variant) and not flat:
        try:
            crossing = next(iter(_crossings(_build_surface(inp.grid), inp.outline_2180, leaving=True)), None)
        except ValueError:
            crossing = None
    wet_boundary, wet_interior = (
        _wet_points(inp) if "ndmi" in (outlet_variant, basin_variant) else (None, None)
    )
    ctx = _Context(
        inp,
        plane,
        flat,
        _slope_text(plane.slope_pct),
        None if flat else _lower_edge(inp, plane),
        outlet_variant,
        basin_variant,
        crossing,
        wet_boundary,
        wet_interior,
    )
    outlet = _outlet_place(ctx)
    outlet_ha = outlet.catchment_ha
    candidates = [outlet, _strip_place(ctx, outlet_ha), _basin_place(ctx)]
    for extra in (_tillage_place(ctx), _weir_place(ctx, outlet_ha)):
        if extra is not None:
            candidates.append(extra)
    return candidates + _water_candidates(inp, ctx.edge)
