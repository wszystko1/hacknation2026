"""Terrain model of a parcel: its catchment, where the water leaves, where it collects.

Input is the elevation grid of the parcel plus about 300 m around it (10 m step) and the outline. The grid is
filled and drained and each cell sends its water to the steepest lower neighbour (D8, see `placement`). From that:

* catchment of the parcel in ha: every cell whose flow path ends inside the outline, the parcel included;
* `catchment_truncated`: the catchment reaches the edge of the grid, so water from beyond it is not counted and
  the number is a lower bound;
* the outflow segment: the shortest part of the outline through which at least `OUTFLOW_SHARE` of the water
  that leaves the parcel flows. 80% is the team's proposal: the whole flow through one point would hide that sheet
  flow leaves along a side, and the whole outline would say nothing about where to put a grass strip;
* the lowest point of the outline and of the interior;
* depression regions inside the parcel: connected cells that fill up before water spills over, each with its
  outline, depth (m) and volume (m3);
* the distance to the nearest BDOT10k ditch.

A plane that falls less than the smallest slope of the catalogue is below the resolution of the heights (rounded to
0.1 m): there the flow direction is noise, so the model gives the lowest boundary point and says so. Without the
margin grid the model gives the lowest boundary point of the parcel's own grid and the reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from app.advice import placement as pl

# Share of the water leaving the parcel that the outflow segment must carry. Team proposal; shown in the adviser view.
OUTFLOW_SHARE = 0.8

# Smallest fill depth (m) that counts as a depression: the heights are rounded to 0.1 m, so less is rounding.
MIN_DEPRESSION_DEPTH_M = 0.1

FLAT_FLAG = "spadek poniżej rozdzielczości"


@dataclass
class DepressionRegion:
    outline_2180: list[list[float]]  # convex hull of the cell corners, [x, y]
    depth_m: float
    volume_m3: float
    area_m2: float
    lowest_point_2180: list[float]


@dataclass
class OutflowSegment:
    points_2180: list[list[float]]  # part of the outline, a point every grid step
    length_m: float
    share: float  # share of the leaving water it carries, 0..1
    middle_2180: list[float]


@dataclass
class TerrainModel:
    catchment_ha: float | None = None
    catchment_truncated: bool | None = None  # None when there is no catchment
    slope_pct: float | None = None
    flags: list[str] = field(default_factory=list)  # FLAT_FLAG
    outflow: OutflowSegment | None = None
    lowest_boundary_2180: list[float] | None = None
    lowest_interior_2180: list[float] | None = None
    depressions: list[DepressionRegion] = field(default_factory=list)
    ditch_distance_m: float | None = None
    reason: str = ""  # why something is missing, in Polish

    def line(self) -> str:
        """The adviser's one line about the catchment, or the reason it is missing."""
        if self.catchment_ha is None:
            return f"Zlewnia: brak, bo {self.reason or 'brak danych'}"
        cut = "tak" if self.catchment_truncated else "nie"
        text = f"Zlewnia: {_num(self.catchment_ha, 1)} ha (ucięta przez siatkę: {cut})"
        if self.outflow is not None:
            p = self.outflow.middle_2180
            text += (
                f", wypływ przez odcinek granicy {_num(self.outflow.length_m, 0)} m "
                f"({_num(100 * self.outflow.share, 0)}% strumienia, ≥{round(100 * OUTFLOW_SHARE)}%), "
                f"środek E {p[0]:.0f} N {p[1]:.0f} (EPSG:2180)"
            )
        elif self.reason:
            text += f", bez odcinka wypływu, bo {self.reason}"
        return text


def _num(value: float, digits: int) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


# --------------------------------------------------------------------------------------------------------------


def _catchment_mask(s: pl._Surface) -> np.ndarray:
    """Cells whose flow path reaches a cell inside the parcel (those cells included)."""
    reach = s.inside.ravel().copy()
    to = s.flow.to
    for i in np.argsort(s.drained.ravel(), kind="stable").tolist():  # lowest first: a receiver is lower
        j = int(to[i])
        if j >= 0 and reach[j]:
            reach[i] = True
    return reach.reshape(s.rows, s.cols)


def _touches_edge(mask: np.ndarray) -> bool:
    """True when the mask has a cell in the two outermost rings of the grid."""
    return bool(mask[:2, :].any() or mask[-2:, :].any() or mask[:, :2].any() or mask[:, -2:].any())


def _outflow(s: pl._Surface, ring: list[list[float]]) -> OutflowSegment | None:
    """Shortest circular part of the outline that carries OUTFLOW_SHARE of the water leaving the parcel."""
    inside = s.inside.ravel()
    to, acc = s.flow.to, s.flow.acc_ha
    src = np.flatnonzero((to >= 0) & inside)
    src = src[~inside[to[src]]]
    if not len(src):
        return None
    pts = pl._dense(ring, s.step)
    if len(pts) > 1 and np.allclose(pts[0], pts[-1]):
        pts = pts[:-1]
    weights: dict[int, float] = {}
    for a in src.tolist():
        x, y = pl._segment_hit(s.xy(a), s.xy(int(to[a])), ring)
        k = int(np.hypot(pts[:, 0] - x, pts[:, 1] - y).argmin())
        weights[k] = weights.get(k, 0.0) + float(acc[a])
    total = sum(weights.values())
    n = len(pts)
    keys = sorted(weights)
    best: tuple[int, int, float] | None = None  # (start, span in points, carried)
    for i, start in enumerate(keys):
        carried = 0.0
        for off in range(len(keys)):
            k = keys[(i + off) % len(keys)]
            carried += weights[k]
            if carried >= OUTFLOW_SHARE * total - 1e-9:
                span = (k - start) % n + 1
                if best is None or span < best[1] or (span == best[1] and carried > best[2]):
                    best = (start, span, carried)
                break
    assert best is not None
    start, span, carried = best
    run = pts[[(start + o) % n for o in range(span)]]
    length = float(np.hypot(*np.diff(run, axis=0).T).sum()) if span > 1 else float(s.step)
    mid = run[span // 2]
    return OutflowSegment(
        [pl._round_point(x, y) for x, y in run],
        round(max(length, s.step), 1),
        round(carried / total, 3),
        pl._round_point(*mid),
    )


def _hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    pts = sorted(set(points))
    if len(pts) < 3:
        return pts

    def half(seq: list[tuple[float, float]]) -> list[tuple[float, float]]:
        out: list[tuple[float, float]] = []
        for p in seq:
            while (
                len(out) >= 2
                and (
                    (out[-1][0] - out[-2][0]) * (p[1] - out[-2][1])
                    - (out[-1][1] - out[-2][1]) * (p[0] - out[-2][0])
                )
                <= 0
            ):
                out.pop()
            out.append(p)
        return out

    lower, upper = half(pts), half(pts[::-1])
    return lower[:-1] + upper[:-1]


def _depression_regions(s: pl._Surface) -> list[DepressionRegion]:
    """Connected inside cells that the flood filled by at least MIN_DEPRESSION_DEPTH_M."""
    raw = pl._heights(s.grid)
    fill = np.where(np.isfinite(raw), s.drained - raw, 0.0)
    wet = s.inside & (fill >= MIN_DEPRESSION_DEPTH_M)
    cells = np.flatnonzero(wet.ravel()).tolist()
    out: list[DepressionRegion] = []
    h = s.step / 2.0
    for group in pl._clusters(cells, s.cols):
        members = [cells[k] for k in group]
        depths = np.array([fill.ravel()[m] for m in members])
        centres = [s.xy(m) for m in members]
        corners = [(x + dx, y + dy) for x, y in centres for dx in (-h, h) for dy in (-h, h)]
        hull = _hull(corners)
        lowest = centres[int(depths.argmax())]
        out.append(
            DepressionRegion(
                [[round(x, 1), round(y, 1)] for x, y in hull + hull[:1]],
                round(float(depths.max()), 2),
                round(float(depths.sum()) * s.step * s.step, 1),
                round(len(members) * s.step * s.step, 1),
                pl._round_point(*lowest),
            )
        )
    out.sort(key=lambda r: -r.volume_m3)
    return out


def _ditch_distance(inp: pl.PlacementInput) -> float | None:
    outline = pl._dense(inp.outline_2180, pl.POINT_SPACING_M)
    best: float | None = None
    for feature in inp.water:
        if feature.kind != "ditch":
            continue
        pts = pl._water_points(feature)
        if not len(pts):
            continue
        d = float(
            np.hypot(pts[:, None, 0] - outline[None, :, 0], pts[:, None, 1] - outline[None, :, 1]).min()
        )
        best = d if best is None else min(best, d)
    return None if best is None else round(best, 1)


def _lowest_only(inp: pl.PlacementInput, model: TerrainModel) -> TerrainModel:
    """The fallback: the lowest boundary point from the grid at hand, else the one measured with the parcel."""
    model.lowest_boundary_2180 = pl.lowest_boundary_point(inp) or (
        pl._round_point(*inp.lowest_outline_point_2180) if inp.lowest_outline_point_2180 else None
    )
    model.lowest_interior_2180 = pl.lowest_interior_point(inp)
    model.ditch_distance_m = _ditch_distance(inp)
    return model


def build_terrain_model(
    inp: pl.PlacementInput, *, margin_grid: bool, missing_reason: str = ""
) -> TerrainModel:
    """The terrain model of `inp.grid`. `margin_grid` says the grid is the one with the ~300 m margin; without it the
    catchment is not computed and `missing_reason` (or a default) says why. Never raises for missing data."""
    model = TerrainModel()
    if inp.grid is None:
        model.reason = missing_reason or "brak siatki wysokości dla działki"
        return _lowest_only(inp, model)
    if not margin_grid:
        model.reason = missing_reason or "nie pobrano siatki zlewni; liczymy tylko najniższy punkt granicy"
        return _lowest_only(inp, model)
    try:
        plane = pl.fit_plane(inp.grid)
        surface = pl._build_surface(inp.grid)
    except ValueError:
        model.reason = "w siatce brakuje wysokości dla działki"
        return _lowest_only(inp, model)
    model.slope_pct = round(plane.slope_pct, 2)
    model.lowest_boundary_2180 = pl.lowest_boundary_point(inp)
    model.lowest_interior_2180 = pl.lowest_interior_point(inp)
    model.ditch_distance_m = _ditch_distance(inp)
    model.depressions = _depression_regions(surface)
    if pl._too_flat(plane):
        model.flags.append(FLAT_FLAG)
        model.reason = (
            f"spadek {pl._slope_text(plane.slope_pct)}% jest poniżej rozdzielczości danych (wysokości co 0,1 m), "
            "więc kierunek spływu byłby szumem; podajemy najniższy punkt granicy"
        )
        return model
    mask = _catchment_mask(surface)
    model.catchment_ha = round(float(mask.sum()) * surface.step**2 / 10_000.0, 2)
    model.catchment_truncated = _touches_edge(mask)
    model.outflow = _outflow(surface, inp.outline_2180)
    if model.outflow is None:
        model.reason = "z działki nie wypływa woda w obrębie siatki"
    return model
