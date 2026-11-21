"""Runoff analysis and the places where an action goes on a parcel.

Input: the parcel outline, an elevation grid with a ~300 m margin and the BDOT10k water features. Output: outlets and
inlets on the boundary with their catchment in ha, concentrated flow lines, and candidate places sorted by the
catchment they intercept. Only numpy: the module has no dependency that fails to install on Windows, and it can be
replaced without touching the rest of the report.

Method. Depressions shallower than `FILL_DEPTH_M` are filled with a priority flood (Barnes 2014 scheme, our own code);
deeper ones stay and hold water, as in the ACPF manual (Porter et al. 2025, v7.0). Flats left by filling get a
tiny gradient towards the spill point, so every cell has a direction. Accumulation is either D8 (one direction per
cell, the steepest descent, ties go to the first of E, NE, N, ... so the result is deterministic) or Tarboton's
D-infinity (1997). Accumulation is the upstream area in ha. The stream power index is ln(SCA * tan(slope)), with
SCA taken from D-infinity.

Placement thresholds (stream power index, length of a waterway, slope bands, ditch distance, head of a weir) are read
from `catalog_retencja.csv` through `load_catalog()` at every call, not kept here.
"""

from __future__ import annotations

import json
import math
from collections import deque
from dataclasses import dataclass, field
from heapq import heapify, heappop, heappush
from pathlib import Path
from typing import Literal

import numpy as np
from pyproj import Transformer

from app.advice import catalog as _catalog
from app.advice.catalog import CatalogRow
from app.geodata import ElevationGrid, WaterFeature
from app.models import Place

_TO_LONLAT = Transformer.from_crs("EPSG:2180", "EPSG:4326", always_xy=True)

# Depressions up to this deep are artefacts of the heights (rounded to 0.1 m) and are filled; deeper ones are kept.
# ACPF v7.0 manual, PDF page 18: maximum fill depth "consistent with the vertical accuracy, often 0.1-0.3 m".
FILL_DEPTH_M = 0.2

# Upstream area from which a cell counts as concentrated flow (a flow line).
# ACPF v7.0 manual, PDF page 21: 1-10 acres (0.4-4 ha) suggested; we take 1 ha, the middle of that range.
FLOW_LINE_MIN_HA = 1.0

# Parcel slope (percent) below which no flow direction is shown: heights rounded to 0.1 m on 10 m cells cannot tell
# a 0.5% slope from noise. Team proposal, to check on parcels with surveyed heights.
FLAT_SLOPE_PCT = 0.5

# Height added per cell when a flat is drained towards its spill point (metres). Team proposal: far below the
# 0.1 m rounding of the heights, and a 1000-cell flat still raises less than 1 mm.
FLAT_GRADIENT_M = 1e-6

# How many outlets get a grass strip and a basin. Team proposal: the report shows at most 3 actions per group.
MAX_OUTLETS = 3

# How many separate waterway reaches are reported. Team proposal: same reason as MAX_OUTLETS.
MAX_WATERWAYS = 3

# Length of ditch (metres, each side of the point nearest the outlet) used to count weirs and the ditch slope.
# Team proposal: the grid margin is 300 m, so 150 m each side stays inside the grid.
DITCH_REACH_M = 150.0

# Where `make eval` writes the hit rates of the outlet methods (read from the working directory).
METRICS_PATH = Path("metrics.json")

Method = Literal["d8", "dinf"]
OutletMethod = Literal["d8", "dinf", "lowest"]

# (row step, column step) of E, NE, N, NW, W, SW, S, SE.
_OFFS = ((0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1), (1, 0), (1, 1))
# D-infinity facets: (cardinal neighbour, diagonal neighbour) as indices into _OFFS (Tarboton 1997, table 1).
_FACETS = ((0, 1), (2, 1), (2, 3), (4, 3), (4, 5), (6, 5), (6, 7), (0, 7))


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
    kind: str  # "punkt wypływu", "rów zadarniony", "pas konturowy", "pas trawy", "zastawka", "niecka", "rów", ...
    place: Place | None
    reason: str = ""  # why there is no place ("teren płaski, spadek 0,3%")
    catchment_ha: float | None = None  # water this action intercepts
    length_m: float | None = None  # waterway reach, boundary strip, ditch reach or contour strip
    slope_pct: float | None = None  # parcel slope, or the slope of the ditch for a weir
    distance_m: float | None = None  # flow line to ditch, or parcel to water
    n_weirs: int | None = None
    bearing_deg: float | None = None  # direction of a strip or of furrows along the contour, 0-180 from north

    @property
    def no_place_reason(self) -> str:
        return f"brak miejsca na działce, bo {self.reason}" if self.reason else ""


# --------------------------------------------------------------------------------------------------------------
# Small public helpers
# --------------------------------------------------------------------------------------------------------------


def stream_power_index(sca_m: float, slope_pct: float) -> float:
    """SPI = ln(SCA * tan(slope)); SCA in m of upstream area per metre of cell width, slope in percent."""
    product = sca_m * slope_pct / 100.0
    return math.log(product) if product > 0 else -math.inf


def weir_count(length_m: float, slope_pct: float, head_m: float) -> int:
    """Weirs needed so each holds back one `head_m` of the fall along `length_m` of ditch."""
    return max(1, round(length_m * slope_pct / 100.0 / head_m))


def outlet_method() -> OutletMethod:
    """The outlet method with the highest hit rate in the ditch test; a tie goes to the simpler one."""
    try:
        data = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "lowest"
    section = data.get("retention") if isinstance(data, dict) else None
    section = section if isinstance(section, dict) else {}
    scores: dict[str, float] = {}
    for name in ("lowest", "d8", "dinf"):  # the order is the tie-break
        value = section.get(f"outlet_hit_{name}")
        if not isinstance(value, int | float) or isinstance(value, bool):
            return "lowest"
        scores[name] = float(value)
    best = max(scores.values())
    return next(name for name in ("lowest", "d8", "dinf") if scores[name] == best)  # type: ignore[return-value]


# --------------------------------------------------------------------------------------------------------------
# Terrain surface: filling, flow directions, accumulation
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
    offs = _OFFS
    while heap:
        h, i = heappop(heap)
        r, c = divmod(i, cols)
        for dr, dc in offs:
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


def _label_positive(mask: np.ndarray) -> tuple[np.ndarray, int]:
    """8-connected labels of the True cells (0 elsewhere)."""
    rows, cols = mask.shape
    labels = np.zeros(mask.shape, dtype=int)
    count = 0
    for r0, c0 in zip(*np.nonzero(mask), strict=True):
        if labels[r0, c0]:
            continue
        count += 1
        labels[r0, c0] = count
        queue = deque([(int(r0), int(c0))])
        while queue:
            r, c = queue.popleft()
            for dr, dc in _OFFS:
                rr, cc = r + dr, c + dc
                if 0 <= rr < rows and 0 <= cc < cols and mask[rr, cc] and not labels[rr, cc]:
                    labels[rr, cc] = count
                    queue.append((rr, cc))
    return labels, count


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
    """Where each cell sends its water: up to two receivers with shares that sum to 1."""

    to1: np.ndarray  # flat index or -1
    to2: np.ndarray
    share1: np.ndarray
    share2: np.ndarray
    acc_ha: np.ndarray  # upstream area including the cell itself, ha


@dataclass
class _Surface:
    grid: ElevationGrid
    rows: int
    cols: int
    step: float
    z: np.ndarray  # as given (nodata filled low)
    filled: np.ndarray  # shallow depressions filled, deep ones kept
    drained: np.ndarray  # `filled` plus the gradient across flats: strictly lower along every flow path
    inside: np.ndarray  # bool
    slope_pct: np.ndarray  # Horn slope of `filled`
    gx: np.ndarray  # dz/dx, dz/dy of `filled` (m/m)
    gy: np.ndarray
    kept_depressions: int
    flows: dict[str, _Flow] = field(default_factory=dict)

    def centre(self, r: float, c: float) -> tuple[float, float]:
        return self.grid.x0 + (c + 0.5) * self.step, self.grid.y_top - (r + 0.5) * self.step

    def xy(self, idx: int) -> tuple[float, float]:
        r, c = divmod(int(idx), self.cols)
        return self.centre(r, c)

    def cell_of(self, x: float, y: float) -> tuple[int, int] | None:
        c = int(math.floor((x - self.grid.x0) / self.step))
        r = int(math.floor((self.grid.y_top - y) / self.step))
        return (r, c) if 0 <= r < self.rows and 0 <= c < self.cols else None


def _build_surface(grid: ElevationGrid) -> _Surface:
    rows, cols = grid.rows, grid.cols
    raw = np.array([[np.nan if v is None else v for v in row] for row in grid.z], dtype=float)
    unknown = np.isnan(raw)
    z = raw.copy()
    if unknown.all():
        raise ValueError("elevation grid without heights")
    z[unknown] = np.nanmin(raw) - 1.0  # water that reaches a cell without height leaves the grid
    inside = np.array(grid.inside, dtype=bool)

    seeds = sorted(set(_edge_cells(rows, cols)) | set(np.flatnonzero(unknown.ravel()).tolist()))
    plain = _flood(z, seeds, 0.0)
    depth = plain - z
    labels, count = _label_positive(depth > 1e-9)
    filled = plain
    sinks: list[int] = []
    kept = 0
    if count:
        keep_label = np.zeros(count + 1, dtype=bool)
        for label in range(1, count + 1):
            region = labels == label
            if depth[region].max() > FILL_DEPTH_M + 1e-9:
                keep_label[label] = True
                idx = np.flatnonzero(region.ravel())
                sinks.append(int(idx[np.argmin(z.ravel()[idx])]))
                kept += 1
        filled = np.where(keep_label[labels], z, plain)
    drained = _flood(filled, sorted(set(seeds) | set(sinks)), FLAT_GRADIENT_M)

    step = float(grid.step_m)
    pad = np.pad(filled, 1, mode="edge")
    a, b, c = pad[:-2, :-2], pad[:-2, 1:-1], pad[:-2, 2:]
    d, f = pad[1:-1, :-2], pad[1:-1, 2:]
    g, h, i = pad[2:, :-2], pad[2:, 1:-1], pad[2:, 2:]
    gx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8 * step)  # rows grow southwards, columns eastwards
    gy_south = ((g + 2 * h + i) - (a + 2 * b + c)) / (8 * step)
    gy = -gy_south  # per metre northwards
    slope_pct = np.hypot(gx, gy) * 100.0
    return _Surface(grid, rows, cols, step, z, filled, drained, inside, slope_pct, gx, gy, kept)


def _flow_directions(s: _Surface, method: Method) -> _Flow:
    w = s.drained
    rows, cols = s.rows, s.cols
    step = s.step
    dist = [step if (dr == 0 or dc == 0) else step * math.sqrt(2.0) for dr, dc in _OFFS]
    nb = [_shifted(w, dr, dc, float(w.max()) + 1e6) for dr, dc in _OFFS]  # beyond the grid: far above
    idx = np.arange(rows * cols).reshape(rows, cols)
    off_idx = [dr * cols + dc for dr, dc in _OFFS]
    edge = np.zeros((rows, cols), dtype=bool)
    edge[0, :] = edge[-1, :] = True
    edge[:, 0] = edge[:, -1] = True

    to1 = np.full((rows, cols), -1, dtype=int)
    to2 = np.full((rows, cols), -1, dtype=int)
    share1 = np.zeros((rows, cols))
    share2 = np.zeros((rows, cols))

    if method == "d8":
        drop = np.stack([(w - n) / d for n, d in zip(nb, dist, strict=True)])
        best = drop.argmax(axis=0)  # the first of equal drops wins: E, NE, N, ...
        best_drop = np.take_along_axis(drop, best[None], axis=0)[0]
        ok = (best_drop > 0) & ~edge
        to1 = np.where(ok, idx + np.array(off_idx)[best], -1)
        share1 = np.where(ok, 1.0, 0.0)
    else:
        facet_slope, facet_to1, facet_to2, facet_p2 = [], [], [], []
        diag = step * math.sqrt(2.0)
        for e1, e2 in _FACETS:
            z1, z2 = nb[e1], nb[e2]
            s1 = (w - z1) / step
            s2 = (z1 - z2) / step
            r = np.arctan2(s2, s1)
            clipped_low = r < 0
            clipped_high = r > math.pi / 4
            r = np.where(clipped_low, 0.0, np.where(clipped_high, math.pi / 4, r))
            slope = np.where(clipped_low, s1, np.where(clipped_high, (w - z2) / diag, np.hypot(s1, s2)))
            facet_slope.append(slope)
            facet_p2.append(r / (math.pi / 4))
            facet_to1.append(idx + off_idx[e1])
            facet_to2.append(idx + off_idx[e2])
        slopes = np.stack(facet_slope)
        best = slopes.argmax(axis=0)
        best_slope = np.take_along_axis(slopes, best[None], axis=0)[0]
        ok = np.isfinite(best_slope) & (best_slope > 0) & ~edge
        p2 = np.take_along_axis(np.stack(facet_p2), best[None], axis=0)[0]
        n1 = np.take_along_axis(np.stack(facet_to1), best[None], axis=0)[0]
        n2 = np.take_along_axis(np.stack(facet_to2), best[None], axis=0)[0]
        p2 = np.clip(np.where(ok, p2, 0.0), 0.0, 1.0)
        use1 = ok & (p2 < 1.0)
        use2 = ok & (p2 > 0.0)
        to1 = np.where(use1, n1, -1)
        to2 = np.where(use2, n2, -1)
        share1 = np.where(use1, 1.0 - p2, 0.0)
        share2 = np.where(use2, p2, 0.0)

    flow = _Flow(to1.ravel(), to2.ravel(), share1.ravel(), share2.ravel(), np.zeros(rows * cols))
    flow.acc_ha = _accumulate(s, flow)
    return flow


def _accumulate(s: _Surface, flow: _Flow) -> np.ndarray:
    """Upstream area in ha: cells from the highest to the lowest pass their water on."""
    cell_ha = s.step * s.step / 10_000.0
    acc = np.full(s.rows * s.cols, cell_ha)
    order = np.argsort(-s.drained.ravel(), kind="stable")
    to1, to2, sh1, sh2 = flow.to1, flow.to2, flow.share1, flow.share2
    for i in order.tolist():
        a = acc[i]
        j = to1[i]
        if j >= 0:
            acc[j] += a * sh1[i]
        j = to2[i]
        if j >= 0:
            acc[j] += a * sh2[i]
    return acc


def _flow(s: _Surface, method: Method) -> _Flow:
    if method not in s.flows:
        s.flows[method] = _flow_directions(s, method)
    return s.flows[method]


# --------------------------------------------------------------------------------------------------------------
# Geometry helpers
# --------------------------------------------------------------------------------------------------------------


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


def _bbox(ring: list[list[float]]) -> tuple[float, float, float, float]:
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    return min(xs), min(ys), max(xs), max(ys)


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


def _where(x: float, y: float, ring: list[list[float]]) -> str:
    """The part of the parcel (a 3 x 3 split of its bounding box) a point lies in, in the locative."""
    x0, y0, x1, y1 = _bbox(ring)
    u = (x - x0) / max(x1 - x0, 1e-9)
    v = (y - y0) / max(y1 - y0, 1e-9)
    col = -1 if u < 1 / 3 else (1 if u > 2 / 3 else 0)
    row = -1 if v < 1 / 3 else (1 if v > 2 / 3 else 0)
    return _COMPASS[(col, row)]


def _place(kind: str, x: float, y: float, description: str, catchment_ha: float | None = None) -> Place:
    lon, lat = _TO_LONLAT.transform(x, y)
    return Place(
        kind=kind,
        x_2180=round(x, 1),
        y_2180=round(y, 1),
        lon=lon,
        lat=lat,
        description=description,
        catchment_ha=None if catchment_ha is None else round(catchment_ha, 2),
    )


def _dense(ring: list[list[float]], spacing: float) -> np.ndarray:
    """Points along a ring every `spacing` metres, vertices included."""
    pts: list[tuple[float, float]] = []
    for (x1, y1), (x2, y2) in zip(ring, ring[1:], strict=False):
        n = max(1, int(math.ceil(math.hypot(x2 - x1, y2 - y1) / spacing)))
        pts += [(x1 + (x2 - x1) * k / n, y1 + (y2 - y1) * k / n) for k in range(n)]
    pts.append((ring[-1][0], ring[-1][1]))
    return np.array(pts)


def _polygon_contains(ring: list[list[float]], x: float, y: float) -> bool:
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:], strict=False):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _slope_text(slope_pct: float) -> str:
    return f"{slope_pct:.1f}".replace(".", ",")


# --------------------------------------------------------------------------------------------------------------
# Public: runoff
# --------------------------------------------------------------------------------------------------------------


def _parcel_slope(s: _Surface, inp: PlacementInput) -> float:
    """Parcel slope in percent: the one the report states when given, else from the grid inside the outline."""
    if inp.slope_mean_pct is not None:
        return inp.slope_mean_pct
    return float(s.slope_pct[s.inside].mean()) if s.inside.any() else float(s.slope_pct.mean())


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
    cells: list[int]  # all cells of the cluster on the inside of the boundary


def _crossings(s: _Surface, flow: _Flow, ring: list[list[float]], leaving: bool) -> list[_Crossing]:
    """Flow across the parcel boundary, in ha, one entry per group of adjacent crossing cells, largest first."""
    inside = s.inside.ravel()
    edges: list[tuple[float, int, int]] = []  # (ha carried, source cell, receiving cell)
    for to, share in ((flow.to1, flow.share1), (flow.to2, flow.share2)):
        src = np.flatnonzero((to >= 0) & (share > 0))
        dst = to[src]
        across = (inside[src] & ~inside[dst]) if leaving else (~inside[src] & inside[dst])
        for a, b in zip(src[across].tolist(), dst[across].tolist(), strict=True):
            edges.append((float(flow.acc_ha[a] * share[a]), a, b))
    if not edges:
        return []
    edges.sort(key=lambda e: -e[0])
    # the cell on the parcel's side of the boundary identifies a crossing; two receivers of one cell merge
    side = [(e[1] if leaving else e[2]) for e in edges]
    cells = list(dict.fromkeys(side))
    out: list[_Crossing] = []
    for group in _clusters(cells, s.cols):
        members = {cells[k] for k in group}
        mine = [e for e, cell in zip(edges, side, strict=True) if cell in members]
        _, a, b = mine[0]  # the largest flow of the group places the point
        x, y = _segment_hit(s.xy(a), s.xy(b), ring)
        total = sum(e[0] for e in mine)
        out.append(
            _Crossing(
                BoundaryPoint(round(x, 1), round(y, 1), round(total, 2)),
                a if leaving else b,
                sorted(members),
            )
        )
    out.sort(key=lambda c: -c.point.catchment_ha)
    return out


def _flow_lines(s: _Surface, flow: _Flow) -> list[list[list[float]]]:
    """Polylines through the cells above the area threshold, head to mouth."""
    on = flow.acc_ha >= FLOW_LINE_MIN_HA
    if not on.any():
        return []
    primary = np.where((flow.share2 > flow.share1) & (flow.to2 >= 0), flow.to2, flow.to1)
    has_upstream = np.zeros(on.shape, dtype=bool)
    src = np.flatnonzero(on & (primary >= 0))
    has_upstream[primary[src]] = True
    visited = np.zeros(on.shape, dtype=bool)
    lines: list[list[list[float]]] = []
    heads = np.flatnonzero(on & ~has_upstream)
    for head in heads.tolist():
        line: list[list[float]] = []
        i = head
        while True:
            x, y = s.xy(i)
            line.append([round(x, 1), round(y, 1)])
            if visited[i]:
                break  # joined a line that is already drawn
            visited[i] = True
            nxt = int(primary[i])
            if nxt < 0 or not on[nxt]:
                break
            i = nxt
        if len(line) > 1:
            lines.append(line)
    return lines


def runoff(inp: PlacementInput, method: Method = "d8") -> Runoff:
    """Outlets, inlets and flow lines of the parcel; `reason` instead of arrows when the slope is too small."""
    if inp.grid is None:
        return Runoff(reason="brak siatki wysokości dla działki")
    try:
        surface = _build_surface(inp.grid)
    except ValueError:
        return Runoff(reason="brak wysokości w siatce dla działki")
    return _runoff(surface, inp, method)


def _runoff(surface: _Surface, inp: PlacementInput, method: Method) -> Runoff:
    slope = _parcel_slope(surface, inp)
    if slope < FLAT_SLOPE_PCT:
        return Runoff(reason=f"spadek {_slope_text(slope)}% jest za mały, by wskazać linię spływu")
    flow = _flow(surface, method)
    ring = inp.outline_2180
    return Runoff(
        outlets=[c.point for c in _crossings(surface, flow, ring, leaving=True)],
        inlets=[c.point for c in _crossings(surface, flow, ring, leaving=False)],
        flow_lines=_flow_lines(surface, flow),
    )


# --------------------------------------------------------------------------------------------------------------
# Public: places
# --------------------------------------------------------------------------------------------------------------


def _water_points(feature: WaterFeature, spacing: float) -> np.ndarray:
    pts = [_dense(ring, spacing) for ring in feature.rings_2180 if len(ring) > 1]
    return np.vstack(pts) if pts else np.empty((0, 2))


def _nearest(points: np.ndarray, x: float, y: float) -> tuple[float, float, float] | None:
    if not len(points):
        return None
    d = np.hypot(points[:, 0] - x, points[:, 1] - y)
    k = int(d.argmin())
    return float(points[k, 0]), float(points[k, 1]), float(d[k])


def _ditch_reach(s: _Surface, pts: np.ndarray, x: float, y: float) -> tuple[float, float | None]:
    """Length of the ditch within DITCH_REACH_M each side of the point nearest (x, y), and its slope in percent."""
    d = np.hypot(pts[:, 0] - x, pts[:, 1] - y)
    near = pts[int(d.argmin())]
    local = pts[np.hypot(pts[:, 0] - near[0], pts[:, 1] - near[1]) <= DITCH_REACH_M]
    if len(local) < 2:
        return 0.0, None
    centred = local - local.mean(axis=0)
    axis = np.linalg.svd(centred, full_matrices=False)[2][0]
    t = centred @ axis
    length = float(t.max() - t.min())
    ends = []
    for sel in (t <= t.min() + s.step, t >= t.max() - s.step):
        heights = []
        for px, py in local[sel]:
            cell = s.cell_of(float(px), float(py))
            if cell is not None:
                heights.append(float(s.filled[cell]))
        ends.append(float(np.mean(heights)) if heights else None)
    if length <= 0 or ends[0] is None or ends[1] is None:
        return length, None
    return length, abs(ends[0] - ends[1]) / length * 100.0


def _lowest_boundary_cell(s: _Surface) -> int | None:
    """The lowest cell inside the parcel that has a neighbour outside it."""
    inside = s.inside
    if not inside.any():
        return None
    border = np.zeros_like(inside)
    for dr, dc in _OFFS:
        border |= inside & ~_shifted(inside.astype(float), dr, dc, 0.0).astype(bool)
    if not border.any():
        border = inside
    heights = np.where(border, s.z, np.inf).ravel()
    return int(heights.argmin())


def _sort_key(c: PlaceCandidate) -> float:
    return -(c.catchment_ha if c.catchment_ha is not None else -1.0)


def _spi_grid(s: _Surface) -> np.ndarray:
    sca = _flow(s, "dinf").acc_ha.reshape(s.rows, s.cols) * 10_000.0 / s.step  # m of upstream area per metre
    tan_b = s.slope_pct / 100.0
    with np.errstate(divide="ignore", invalid="ignore"):
        spi = np.log(sca * tan_b)
    spi[~np.isfinite(spi)] = np.nan
    return spi


def _waterways(s: _Surface, inp: PlacementInput) -> list[PlaceCandidate]:
    """Reaches of concentrated flow inside the parcel where SPI exceeds mean + k * sd, at least `length_min` long."""
    k = _cond("row-zadarniony", "spi_min")
    length_min = _cond("row-zadarniony", "length_min_m")
    if k is None or length_min is None:
        return []
    spi = _spi_grid(s)
    valid = ~np.isnan(spi)
    if valid.sum() < 2:
        return []
    threshold = float(spi[valid].mean() + k * spi[valid].std())
    chosen = valid & (np.nan_to_num(spi, nan=-np.inf) > threshold) & s.inside
    if not chosen.any():
        return []
    labels, count = _label_positive(chosen)
    d8 = _flow(s, "d8")
    order = np.argsort(-s.drained.ravel(), kind="stable")
    flat_labels = labels.ravel()
    acc = d8.acc_ha
    reach = np.zeros(len(flat_labels))  # longest chain of selected cells ending in the cell, metres
    diag = s.step * math.sqrt(2.0)
    for i in order.tolist():
        if not flat_labels[i]:
            continue
        j = int(d8.to1[i])
        if j >= 0 and flat_labels[j] == flat_labels[i]:
            r0, c0 = divmod(i, s.cols)
            r1, c1 = divmod(j, s.cols)
            reach[j] = max(reach[j], reach[i] + (s.step if r0 == r1 or c0 == c1 else diag))
    out: list[PlaceCandidate] = []
    slope = _parcel_slope(s, inp)
    for label in range(1, count + 1):
        members = np.flatnonzero(flat_labels == label)
        mouth = int(members[np.argmax(reach[members])])
        length = float(reach[mouth] + s.step)  # a chain of n cells is n steps long, counting both end cells
        if length < length_min:
            continue
        # walk back up from the mouth along the longest chain to find its middle cell
        chain = [mouth]
        while True:
            ups = [
                m
                for m in members.tolist()
                if int(d8.to1[m]) == chain[-1]
                and abs(reach[m] + _link(s, m, chain[-1]) - reach[chain[-1]]) < 1e-6
            ]
            if not ups:
                break
            chain.append(ups[0])
        mid = chain[len(chain) // 2]
        x, y = s.xy(mid)
        catchment = float(acc[mouth])
        out.append(
            PlaceCandidate(
                kind="rów zadarniony",
                place=_place("rów zadarniony", x, y, _where(x, y, inp.outline_2180), catchment),
                catchment_ha=round(catchment, 2),
                length_m=round(length, 1),
                slope_pct=round(slope, 1),
            )
        )
    out.sort(key=_sort_key)
    return out[:MAX_WATERWAYS]


def _link(s: _Surface, i: int, j: int) -> float:
    r0, c0 = divmod(i, s.cols)
    r1, c1 = divmod(j, s.cols)
    return s.step if r0 == r1 or c0 == c1 else s.step * math.sqrt(2.0)


def _contour_places(s: _Surface, inp: PlacementInput) -> list[PlaceCandidate]:
    """Contour strip and cross-slope tillage where the parcel slope lies in the catalogue band."""
    out: list[PlaceCandidate] = []
    slope = _parcel_slope(s, inp)
    inside = s.inside
    if not inside.any():
        return out
    mean_gx, mean_gy = float(s.gx[inside].mean()), float(s.gy[inside].mean())
    if math.hypot(mean_gx, mean_gy) == 0:
        return out
    # direction along the contour: perpendicular to the mean fall line, as a bearing from north in 0-180
    fall_bearing = math.degrees(math.atan2(-mean_gx, -mean_gy)) % 360.0
    bearing = (fall_bearing + 90.0) % 180.0
    ux, uy = math.sin(math.radians(bearing)), math.cos(math.radians(bearing))
    rr, cc = np.nonzero(inside)
    xs = s.grid.x0 + (cc + 0.5) * s.step
    ys = s.grid.y_top - (rr + 0.5) * s.step
    along = xs * ux + ys * uy
    length = float(along.max() - along.min() + s.step)
    centre = int(np.argmin(np.hypot(xs - xs.mean(), ys - ys.mean())))
    cx, cy = float(xs[centre]), float(ys[centre])
    cell = (int(rr[centre]), int(cc[centre]))
    catchment = float(_flow(s, "d8").acc_ha[cell[0] * s.cols + cell[1]])
    for action_id, kind in (
        ("pas-konturowy", "pas konturowy"),
        ("uprawa-w-poprzek-stoku", "uprawa w poprzek stoku"),
    ):
        low, high = _cond(action_id, "slope_min_pct"), _cond(action_id, "slope_max_pct")
        if low is None or high is None or not (low <= slope <= high):
            continue
        out.append(
            PlaceCandidate(
                kind=kind,
                place=_place(kind, cx, cy, _where(cx, cy, inp.outline_2180), catchment),
                catchment_ha=round(catchment, 2),
                length_m=round(length, 1),
                slope_pct=round(slope, 1),
                bearing_deg=round(bearing, 0),
            )
        )
    return out


def _towards_outside(s: _Surface, cell: int, ring: list[list[float]]) -> tuple[float, float]:
    """Where the lowest neighbour outside the parcel meets the outline, seen from a cell inside it."""
    r, c = divmod(cell, s.cols)
    outside = [
        (float(s.z[r + dr, c + dc]), r + dr, c + dc)
        for dr, dc in _OFFS
        if 0 <= r + dr < s.rows and 0 <= c + dc < s.cols and not s.inside[r + dr, c + dc]
    ]
    if not outside:
        return s.xy(cell)
    _, rr, cc = min(outside)
    return _segment_hit(s.xy(cell), s.centre(rr, cc), ring)


def _outlet_candidates(s: _Surface, inp: PlacementInput, method: OutletMethod) -> list[_Crossing]:
    """Outlets by the chosen method; for "lowest" one outlet at the lowest boundary point."""
    ring = inp.outline_2180
    if method != "lowest":
        return _crossings(s, _flow(s, method), ring, leaving=True)
    if inp.lowest_outline_point_2180 is not None:
        x, y = inp.lowest_outline_point_2180
        cell = s.cell_of(x, y)
        flat_cell = None if cell is None else cell[0] * s.cols + cell[1]
    else:
        flat_cell = _lowest_boundary_cell(s)
        x, y = s.xy(flat_cell) if flat_cell is not None else (0.0, 0.0)
        if flat_cell is not None:
            x, y = _towards_outside(s, flat_cell, ring)
    if flat_cell is None:
        return []
    r, c = divmod(flat_cell, s.cols)
    block = [
        rr * s.cols + cc
        for rr in range(max(r - 1, 0), min(r + 2, s.rows))
        for cc in range(max(c - 1, 0), min(c + 2, s.cols))
    ]
    acc = _flow(s, "d8").acc_ha
    best = max(block, key=lambda i: acc[i])
    inside_block = [i for i in block if s.inside.ravel()[i]]
    inside_cell = max(inside_block, key=lambda i: acc[i]) if inside_block else best
    return [
        _Crossing(
            BoundaryPoint(round(x, 1), round(y, 1), round(float(acc[best]), 2)), inside_cell, [inside_cell]
        )
    ]


def _boundary_length(s: _Surface, cells: list[int]) -> float:
    pts = np.array([s.xy(i) for i in cells])
    span = max(float(np.hypot(*(pts.max(axis=0) - pts.min(axis=0)))), 0.0)
    return span + s.step


def _water_candidates(
    s: _Surface | None, inp: PlacementInput, outlet: _Crossing | None
) -> list[PlaceCandidate]:
    """Ditches and ponds from BDOT10k: a weir where the flow line reaches a ditch, the ditch itself, a pond."""
    out: list[PlaceCandidate] = []
    ditch_max = _cond("zastawka-nowa", "ditch_max_m")
    head = _cond("zastawka-nowa", "head_m")
    rebuild_max = _cond("przebudowa-rowu", "ditch_max_m")
    pond_max = _cond("ochrona-zbiornika", "ditch_max_m")
    ring = inp.outline_2180
    x0, y0, x1, y1 = _bbox(ring)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    spacing = s.step / 2 if s else 5.0
    for feature in inp.water:
        pts = _water_points(feature, spacing)
        if feature.kind == "ditch":
            ref = (outlet.point.x_2180, outlet.point.y_2180) if outlet else (cx, cy)
            hit = _nearest(pts, *ref)
            if hit is None:
                continue
            hx, hy, dist = hit
            length, slope = _ditch_reach(s, pts, hx, hy) if s else (0.0, None)
            catchment = outlet.point.catchment_ha if outlet and dist <= (ditch_max or 0) else None
            if (
                outlet is not None
                and ditch_max is not None
                and head
                and dist <= ditch_max
                and outlet.point.catchment_ha >= FLOW_LINE_MIN_HA
            ):
                n = weir_count(length, slope, head) if slope is not None else None
                out.append(
                    PlaceCandidate(
                        kind="zastawka",
                        place=_place("zastawka", hx, hy, f"rowie przy {_where(hx, hy, ring)}", catchment),
                        catchment_ha=catchment,
                        length_m=round(length, 1),
                        slope_pct=None if slope is None else round(slope, 2),
                        distance_m=round(dist, 1),
                        n_weirs=n,
                    )
                )
            if rebuild_max is not None and feature.distance_m <= rebuild_max:
                out.append(
                    PlaceCandidate(
                        kind="rów",
                        place=_place("rów", hx, hy, f"rowie przy {_where(hx, hy, ring)}", catchment),
                        catchment_ha=catchment,
                        length_m=round(length, 1),
                        slope_pct=None if slope is None else round(slope, 2),
                        distance_m=round(feature.distance_m, 1),
                    )
                )
        elif feature.kind == "water_body" and pond_max is not None and feature.distance_m <= pond_max:
            hit = _nearest(pts, cx, cy)
            if hit is None:
                continue
            out.append(
                PlaceCandidate(
                    kind="zbiornik",
                    place=_place(
                        "zbiornik", hit[0], hit[1], f"zbiorniku przy {_where(hit[0], hit[1], ring)}"
                    ),
                    distance_m=round(feature.distance_m, 1),
                )
            )
    return out


def find_places(inp: PlacementInput) -> list[PlaceCandidate]:
    """Candidate places for retention actions, the ones that intercept the most water first.

    "punkt wypływu" is always present: with a place, or with the reason there is none. Other kinds appear only when
    the geometry gives them a place.
    """
    surface: _Surface | None = None
    if inp.grid is not None:
        try:
            surface = _build_surface(inp.grid)
        except ValueError:
            surface = None
    method = outlet_method()
    candidates: list[PlaceCandidate] = []

    if surface is None:
        outlet_cand = _outlet_without_grid(inp)
        candidates.append(outlet_cand)
        candidates += _water_candidates(None, inp, None)
        return sorted(candidates, key=_sort_key)

    slope = _parcel_slope(surface, inp)
    flat = slope < FLAT_SLOPE_PCT
    ring = inp.outline_2180
    outlets = _outlet_candidates(surface, inp, "lowest" if flat and method != "lowest" else method)
    if flat and method != "lowest":
        candidates.append(
            PlaceCandidate(
                kind="punkt wypływu", place=None, reason=f"teren płaski, spadek {_slope_text(slope)}%"
            )
        )
        outlets = []
    elif outlets:
        top = outlets[0]
        x, y = top.point.x_2180, top.point.y_2180
        text = "najniższy punkt obrysu" if method == "lowest" or flat else _where(x, y, ring)
        candidates.append(
            PlaceCandidate(
                kind="punkt wypływu",
                place=_place("punkt wypływu", x, y, text, top.point.catchment_ha),
                catchment_ha=top.point.catchment_ha,
            )
        )
    else:
        candidates.append(
            PlaceCandidate(kind="punkt wypływu", place=None, reason="woda nie wypływa z działki po stoku")
        )

    if flat:
        candidates += _water_candidates(surface, inp, outlets[0] if outlets else None)
        return sorted(candidates, key=_sort_key)

    candidates += _waterways(surface, inp)
    for crossing in outlets[:MAX_OUTLETS]:
        x, y = crossing.point.x_2180, crossing.point.y_2180
        candidates.append(
            PlaceCandidate(
                kind="pas trawy",
                place=_place("pas trawy", x, y, _where(x, y, ring), crossing.point.catchment_ha),
                catchment_ha=crossing.point.catchment_ha,
                length_m=round(_boundary_length(surface, crossing.cells), 1),
            )
        )
    if outlets:
        top = outlets[0]
        bx, by = surface.xy(top.inside_cell)
        candidates.append(
            PlaceCandidate(
                kind="niecka",
                place=_place("niecka", bx, by, _where(bx, by, ring), top.point.catchment_ha),
                catchment_ha=top.point.catchment_ha,
                length_m=None,
            )
        )
    candidates += _water_candidates(surface, inp, outlets[0] if outlets else None)
    candidates += _contour_places(surface, inp)
    return sorted(candidates, key=_sort_key)


def _outlet_without_grid(inp: PlacementInput) -> PlaceCandidate:
    if inp.lowest_outline_point_2180 is None:
        return PlaceCandidate(kind="punkt wypływu", place=None, reason="brak siatki wysokości dla działki")
    x, y = inp.lowest_outline_point_2180
    return PlaceCandidate(kind="punkt wypływu", place=_place("punkt wypływu", x, y, "najniższy punkt obrysu"))
