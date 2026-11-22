"""Elevation of the parcel and its surroundings: grid plus summary statistics.

Provider chain, most useful first:
1. GUGiK height service (GetHByPointList): the national 1 m terrain model sampled on a regular grid.
2. GUGiK NMT through WCS (same model as a raster), when the point service fails.
3. Open-Meteo Elevation API (Copernicus GLO-90, 90 m); status `fallback`.
"""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass

import numpy as np

from . import cache, config, http, sanity
from .errors import CacheMiss, GeodataError, UpstreamError
from .models import ElevationGrid, Parcel, SourceResult, Terrain, from_dict, now_iso
from .parcel import to_wgs84

RES_POINTS = "GUGiK NMT 1 m model sampled on a regular grid (heights rounded to 0.1 m by the service)"
RES_WCS = "GUGiK NMT 1 m grid (PL-KRON86-NH heights), resampled for the request"
RES_FALLBACK = "Copernicus DEM GLO-90 (90 m) via Open-Meteo Elevation API; slope is indicative only"
MAX_GRID = 160
MAX_POINTS = 4000
CHUNK = 1000


def _frame(parcel: Parcel, pad: float) -> tuple[float, float, float, float]:
    xmin, ymin, xmax, ymax = parcel.bbox_2180
    return xmin - pad, ymin - pad, xmax + pad, ymax + pad


def grid_layout(
    parcel: Parcel, spacing: float, margin: float, max_points: int
) -> tuple[float, float, float, int, int]:
    """x0, y_top, step, rows, cols of a grid over the parcel bbox plus margin, widened to stay under max_points."""
    xmin, ymin, xmax, ymax = _frame(parcel, margin)
    step = spacing
    width, height = xmax - xmin, ymax - ymin
    if math.ceil(width / step) * math.ceil(height / step) > max_points:
        step = math.ceil(math.sqrt(width * height / max_points) * 10) / 10 + 0.1
    cols, rows = max(3, math.ceil(width / step)), max(3, math.ceil(height / step))
    cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
    return round(cx - cols * step / 2, 2), round(cy + rows * step / 2, 2), step, rows, cols


def _slope_field(z: np.ndarray, step: float) -> np.ndarray:
    """Slope in percent per cell from central differences; NaN where a neighbour has no height.

    Gaps are NOT filled (an earlier version filled them with the grid mean and produced slopes of 100-2000 %
    at the edge of the data); a cell next to a gap simply has no slope.
    """
    dy, dx = np.gradient(z, step)
    return np.hypot(dx, dy) * 100.0


def _slope_check(
    z: np.ndarray, step: float, mask: np.ndarray
) -> tuple[float | None, float | None, sanity.Check]:
    """Mean and maximum slope over the cells of `mask` and the verdict on them (value kept even when invalid)."""
    if min(z.shape) < 3:
        return None, None, sanity.invalid("spadek niewiarygodny: siatka za mała", "spadek terenu")
    slope = _slope_field(z, step)[mask]
    finite = np.isfinite(slope)
    if not finite.any():
        return (
            None,
            None,
            sanity.invalid("spadek niewiarygodny: brak sąsiednich komórek z danymi", "spadek terenu"),
        )
    share = float(finite.sum()) / max(int(mask.sum()), 1)
    mean, peak = round(float(slope[finite].mean()), 2), round(float(slope[finite].max()), 2)
    return mean, peak, sanity.guarded("spadek terenu", sanity.check_slope, mean, peak, share)


def _slope_stats(z: np.ndarray, step: float, mask: np.ndarray) -> tuple[float | None, float | None]:
    """Mean and maximum slope over the cells of `mask`; None (missing) when the verdict is invalid."""
    mean, peak, verdict = _slope_check(z, step, mask)
    return (mean, peak) if verdict.usable else (None, None)


def grid_stats(
    z: np.ndarray,
    x0: float,
    y_top: float,
    step: float,
    parcel: Parcel,
    provider: str,
    *,
    keep_grid: bool = True,
) -> Terrain:
    """Statistics from a north-up elevation grid: z[row, col], cell centre (x0 + (col+.5)*step, y_top - (row+.5)*step)."""
    from rasterio.features import geometry_mask
    from rasterio.transform import from_origin

    z = sanity.mask_nodata(
        np.asarray(z, dtype="float64")
    )  # nodata markers and the service's 0.0 gaps become NaN
    transform = from_origin(x0, y_top, step, step)
    geometry = {"type": "Polygon", "coordinates": [parcel.rings_2180[0]]}
    inside = geometry_mask([geometry], out_shape=z.shape, transform=transform, invert=True)
    if inside.sum() < 4:
        inside = geometry_mask(
            [geometry], out_shape=z.shape, transform=transform, invert=True, all_touched=True
        )
    valid = np.isfinite(z)
    mask = inside & valid
    if not mask.any():
        # Never describe the surroundings as the parcel: no valid cell inside the outline means no terrain.
        raise UpstreamError("elevation grid has no valid cells inside the parcel outline")
    dem = sanity.check_dem(z, inside)
    if not dem.usable:
        raise UpstreamError(dem.reason)
    slope_mean, slope_max = _slope_stats(z, step, mask)
    # Lowest point of the outline: walk the ring in steps of one cell and take the lowest cell.
    lowest: tuple[float, float, float] | None = None
    ring = parcel.rings_2180[0]
    for (xa, ya), (xb, yb) in zip(ring[:-1], ring[1:], strict=True):
        n = max(1, int(math.hypot(xb - xa, yb - ya) / step))
        for i in range(n):
            x, y = xa + (xb - xa) * i / n, ya + (yb - ya) * i / n
            col, row = int((x - x0) / step), int((y_top - y) / step)
            if 0 <= row < z.shape[0] and 0 <= col < z.shape[1] and valid[row, col]:
                if lowest is None or z[row, col] < lowest[2]:
                    lowest = (x, y, float(z[row, col]))
    grid = None
    if keep_grid:
        grid = ElevationGrid(
            crs="EPSG:2180", x0=round(x0, 2), y_top=round(y_top, 2), step_m=round(step, 3), rows=z.shape[0],
            cols=z.shape[1], z=[[None if not np.isfinite(v) else round(float(v), 2) for v in row] for row in z],
            inside=inside.astype(int).tolist(),
        )  # fmt: skip
    return Terrain(
        min_m=round(float(z[mask].min()), 2), max_m=round(float(z[mask].max()), 2),
        mean_m=round(float(z[mask].mean()), 2), slope_mean_pct=slope_mean, slope_max_pct=slope_max,
        lowest_outline_point_2180=[round(lowest[0], 2), round(lowest[1], 2)] if lowest else None,
        lowest_outline_point_4326=to_wgs84(lowest[0], lowest[1]) if lowest else None,
        lowest_outline_elevation_m=round(lowest[2], 2) if lowest else None,
        grid_m=round(step, 2), samples=int((inside & valid).sum()), provider=provider, grid=grid,
    )  # fmt: skip


def _grid_array(grid: ElevationGrid) -> np.ndarray:
    return np.array([[np.nan if v is None else v for v in row] for row in grid.z], dtype="float64")


def assess_terrain(parcel: Parcel, terrain: Terrain) -> tuple[Terrain, list[str]]:
    """Plausibility of a terrain result (fresh or from the cache): the verdicts as Polish notes.

    A cached answer written before nodata was recognised is recomputed from its own grid. An invalid slope is
    removed (None) with the note "brak: ..."; a warning leaves the numbers and adds "Ostrzeżenie: ...". Raises
    UpstreamError when the elevations themselves are unusable. A failing check is reported as a gap, never raised.
    """
    notes: list[str] = []
    grid = terrain.grid
    if grid is None:
        return terrain, notes
    z = _grid_array(grid)
    clean = sanity.mask_nodata(z)
    if (
        int(np.isfinite(clean).sum()) != int(np.isfinite(z).sum())
        or terrain.slope_mean_pct is not None
        and not (sanity.check_slope(terrain.slope_mean_pct, terrain.slope_max_pct).usable)
    ):
        fresh = grid_stats(clean, grid.x0, grid.y_top, grid.step_m, parcel, terrain.provider)
        fresh.catchment_grid, fresh.catchment_note = terrain.catchment_grid, terrain.catchment_note
        terrain = fresh
        notes.append("Model terenu: komórki bez danych (0 m) pominięte, statystyki policzone od nowa")
        grid, z = terrain.grid, sanity.mask_nodata(_grid_array(terrain.grid))  # type: ignore[arg-type,union-attr]
    inside = np.array(grid.inside, dtype=bool)  # type: ignore[union-attr]
    mask = inside & np.isfinite(z)
    dem = sanity.guarded("numeryczny model terenu", sanity.check_dem, z, inside)
    if dem.note:
        notes.append(dem.note)
    if not dem.usable:
        raise UpstreamError(dem.reason)
    mean, _, verdict = _slope_check(z, grid.step_m, mask)
    if verdict.note:
        notes.append(verdict.note)
    if verdict.usable:
        plane = sanity.plane_slope_pct(z, inside, grid.step_m)
        consistency = sanity.guarded("spójność spadku", sanity.check_slope_consistency, mean, plane)
        if consistency.note:
            notes.append(consistency.note)
    else:
        terrain.slope_mean_pct = terrain.slope_max_pct = None
    return terrain, notes


def parse_height_list(text: str, expected: int) -> list[float]:
    """Answer of GetHByPointList: "northing easting height" triples separated by commas, in request order."""
    heights = []
    for item in text.strip().split(","):
        parts = item.split()
        if len(parts) != 3:
            raise UpstreamError(f"height service: unexpected answer: {text[:100]!r}")
        value = float(parts[2])
        heights.append(value if -200 < value < 3000 else math.nan)
    if len(heights) != expected:
        raise UpstreamError(f"height service: {len(heights)} values for {expected} points")
    return heights


def _post_heights(points: list[str], deadline: float | None) -> list[float]:
    """Heights of "northing easting" points, in request order; chunks of CHUNK points on 4 threads."""
    chunks = [points[i : i + CHUNK] for i in range(0, len(points), CHUNK)]

    def fetch(chunk: list[str]) -> list[float]:
        # POST: a GET with more than a few hundred points is refused with HTTP 414.
        resp = http.request(
            "POST", config.NMT_POINTS_URL, data={"request": "GetHByPointList", "list": ",".join(chunk)},
            timeout=8.0, retries=1, deadline=deadline,
        )  # fmt: skip
        if resp.status_code != 200:
            raise UpstreamError(f"height service HTTP {resp.status_code}: {resp.text[:100]}")
        return parse_height_list(resp.text, len(chunk))

    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="geodata-nmt") as pool:
        return [h for part in pool.map(fetch, chunks) for h in part]


def _from_points(
    parcel: Parcel, spacing: float, margin: float, max_points: int, deadline: float | None
) -> tuple[Terrain, str, list[str]]:
    x0, y_top, step, rows, cols = grid_layout(parcel, spacing, margin, max_points)
    notes = []
    if step > spacing + 1e-6:
        notes.append(
            f"grid spacing widened from {spacing:g} m to {step:g} m to keep the request under {max_points} points"
        )
    # The service takes "northing easting" pairs.
    points = [
        f"{y_top - (r + 0.5) * step:.2f} {x0 + (c + 0.5) * step:.2f}"
        for r in range(rows)
        for c in range(cols)
    ]
    heights = _post_heights(points, deadline)
    z = np.array(heights, dtype="float64").reshape(rows, cols)
    if not np.isfinite(z).any():
        raise UpstreamError("height service returned no heights")
    return grid_stats(z, x0, y_top, step, parcel, "gugik-nmt-points"), config.NMT_POINTS_URL, notes


def _from_wcs(parcel: Parcel, margin: float, timeout: float, deadline: float | None) -> tuple[Terrain, str]:
    import rasterio

    xmin, ymin, xmax, ymax = _frame(parcel, margin)
    step = max(1.0, max(xmax - xmin, ymax - ymin) / MAX_GRID)
    cols, rows = max(3, round((xmax - xmin) / step)), max(3, round((ymax - ymin) / step))
    # In this service axis "x" is the easting and "y" the northing of EPSG:2180.
    params = [
        ("SERVICE", "WCS"), ("VERSION", "2.0.1"), ("REQUEST", "GetCoverage"), ("COVERAGEID", config.NMT_COVERAGE),
        ("FORMAT", "image/tiff"), ("SUBSET", f"x({xmin:.2f},{xmax:.2f})"), ("SUBSET", f"y({ymin:.2f},{ymax:.2f})"),
        ("SCALESIZE", f"x({cols}),y({rows})"),
    ]  # fmt: skip
    resp = http.get(config.NMT_WCS_URL, params=params, timeout=timeout, retries=0, deadline=deadline)
    if resp.status_code != 200 or resp.content[:2] not in (b"II", b"MM"):
        raise UpstreamError(f"NMT WCS HTTP {resp.status_code}: {resp.content[:120]!r}")
    with rasterio.MemoryFile(resp.content) as memory, memory.open() as ds:
        z = ds.read(1).astype("float64")
        if ds.nodata is not None:
            z[z == ds.nodata] = np.nan
        z[(z < -500) | (z > 3000)] = np.nan
        t = ds.transform
        if abs(t.a) < 1e-9:
            raise UpstreamError("NMT WCS: raster without georeferencing")
        terrain = grid_stats(z, t.c, t.f, abs(t.a), parcel, "gugik-nmt-wcs")
    return terrain, str(resp.url)


def _from_coarse(parcel: Parcel, margin: float, deadline: float | None) -> tuple[Terrain, str]:
    xmin, ymin, xmax, ymax = _frame(parcel, margin)
    step = max(30.0, max(xmax - xmin, ymax - ymin) / 9.0)
    cols, rows = max(3, math.ceil((xmax - xmin) / step)), max(3, math.ceil((ymax - ymin) / step))
    cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
    x0, y_top = cx - cols * step / 2, cy + rows * step / 2
    points = [
        to_wgs84(x0 + (c + 0.5) * step, y_top - (r + 0.5) * step) for r in range(rows) for c in range(cols)
    ]
    params = {
        "latitude": ",".join(f"{p[1]:.5f}" for p in points),
        "longitude": ",".join(f"{p[0]:.5f}" for p in points),
    }
    resp = http.get(config.OPEN_METEO_ELEVATION_URL, params=params, timeout=6.0, retries=1, deadline=deadline)
    if resp.status_code != 200:
        raise UpstreamError(f"elevation API HTTP {resp.status_code}: {resp.text[:120]}")
    values = resp.json().get("elevation") or []
    if len(values) != len(points):
        raise UpstreamError("elevation API: wrong number of values")
    z = np.array([np.nan if v is None else v for v in values], dtype="float64").reshape(rows, cols)
    return grid_stats(z, x0, y_top, step, parcel, "open-meteo-elevation"), config.OPEN_METEO_ELEVATION_URL


# --- Grid with a margin for D8 accumulation -------------------------------------------------------------
CATCHMENT_MARGIN_M = 300.0
CATCHMENT_MARGINS = (300.0, 250.0, 200.0, 150.0)  # tried in this order until the points fit the budget
CATCHMENT_STEP_M = 10.0
CATCHMENT_COARSE_STEPS = (20.0, 30.0)  # outside the outline, interpolated bilinearly to CATCHMENT_STEP_M
CATCHMENT_BUDGET_S = 25.0
# Points one live download manages in CATCHMENT_BUDGET_S. Measured cost per chunk of CHUNK points is in
# docs/notes/siatka-zlewni-czas.md; 4 chunks run in parallel, a round takes about 6 s.
CATCHMENT_MAX_POINTS = 12000


@dataclass(frozen=True)
class CatchmentPlan:
    """Layout of the margin grid: final grid on a 10 m lattice, optionally coarse outside the outline."""

    x0: float
    y_top: float
    rows: int
    cols: int
    margin_m: float
    coarse_k: int  # 1 = every cell downloaded; 2 or 3 = coarse nodes every k cells outside the fine window
    fine_window: tuple[int, int, int, int]  # row0, row1, col0, col1 (end exclusive) downloaded at every cell

    @property
    def coarse_nodes(self) -> tuple[list[int], list[int]]:
        return _nodes(self.rows, self.coarse_k), _nodes(self.cols, self.coarse_k)

    @property
    def points(self) -> int:
        r0, r1, c0, c1 = self.fine_window
        fine = (r1 - r0) * (c1 - c0)
        if self.coarse_k == 1:
            return fine
        rows, cols = self.coarse_nodes
        return fine + len(rows) * len(cols)


def _nodes(n: int, k: int) -> list[int]:
    nodes = list(range(0, n, k))
    if nodes[-1] != n - 1:
        nodes.append(n - 1)
    return nodes


def catchment_plan(
    parcel: Parcel, max_points: int = CATCHMENT_MAX_POINTS, margin_m: float = CATCHMENT_MARGIN_M
) -> CatchmentPlan:
    """The richest layout that fits max_points: 10 m everywhere, else 20 m, else 30 m outside the parcel bbox,
    else the same with a smaller margin (down to 150 m). The last candidate is returned when nothing fits."""
    step = CATCHMENT_STEP_M
    xmin, ymin, xmax, ymax = parcel.bbox_2180
    plan = None
    for margin in [m for m in CATCHMENT_MARGINS if m <= margin_m] or [margin_m]:
        cols = math.ceil((xmax - xmin + 2 * margin) / step)
        rows = math.ceil((ymax - ymin + 2 * margin) / step)
        x0 = round((xmin + xmax) / 2 - cols * step / 2, 2)
        y_top = round((ymin + ymax) / 2 + rows * step / 2, 2)
        c0 = max(0, int((xmin - 1.5 * step - x0) // step))
        c1 = min(cols, math.ceil((xmax + 1.5 * step - x0) / step))
        r0 = max(0, int((y_top - (ymax + 1.5 * step)) // step))
        r1 = min(rows, math.ceil((y_top - (ymin - 1.5 * step)) / step))
        for k in (1, *(round(c / step) for c in CATCHMENT_COARSE_STEPS)):
            window = (0, rows, 0, cols) if k == 1 else (r0, r1, c0, c1)
            plan = CatchmentPlan(x0, y_top, rows, cols, margin, k, window)
            if plan.points <= max_points:
                return plan
    assert plan is not None
    return plan


def _interpolate(z_nodes: np.ndarray, rows: list[int], cols: list[int], shape: tuple[int, int]) -> np.ndarray:
    """Bilinear interpolation of values on the lattice rows x cols (cell indices) to every cell."""
    by_row = np.array([np.interp(np.arange(shape[1]), cols, line) for line in z_nodes])
    return np.array([np.interp(np.arange(shape[0]), rows, by_row[:, j]) for j in range(shape[1])]).T


def _centre(plan: CatchmentPlan, r: int, c: int) -> str:
    return f"{plan.y_top - (r + 0.5) * CATCHMENT_STEP_M:.2f} {plan.x0 + (c + 0.5) * CATCHMENT_STEP_M:.2f}"


def catchment_points(plan: CatchmentPlan) -> tuple[list[str], list[str]]:
    """Request points: (coarse nodes, fine window) in the order they are read back. Coarse is empty for k = 1."""
    r0, r1, c0, c1 = plan.fine_window
    fine = [_centre(plan, r, c) for r in range(r0, r1) for c in range(c0, c1)]
    if plan.coarse_k == 1:
        return [], fine
    rows, cols = plan.coarse_nodes
    return [_centre(plan, r, c) for r in rows for c in cols], fine


def assemble_catchment(plan: CatchmentPlan, coarse: list[float], fine: list[float]) -> np.ndarray:
    """z[rows, cols] on the 10 m lattice: coarse nodes interpolated, the fine window written over them."""
    r0, r1, c0, c1 = plan.fine_window
    if plan.coarse_k == 1:
        return np.array(fine, dtype="float64").reshape(plan.rows, plan.cols)
    rows, cols = plan.coarse_nodes
    z = _interpolate(
        np.array(coarse, dtype="float64").reshape(len(rows), len(cols)), rows, cols, (plan.rows, plan.cols)
    )
    z[r0:r1, c0:c1] = np.array(fine, dtype="float64").reshape(r1 - r0, c1 - c0)
    return z


def catchment_note(plan: CatchmentPlan) -> str:
    """What was downloaded, in plain Polish."""
    area = f"obrys działki i {plan.margin_m:g} m wokół niego"
    if plan.coarse_k == 1:
        return f"Siatka zlewni: {area}, krok 10 m, {plan.points} punktów z usługi wysokości GUGiK."
    return (
        f"Siatka zlewni: {area}; krok 10 m przy działce, poza nią punkty co {plan.coarse_k * 10} m "
        f"uzupełnione liniowo do kroku 10 m ({plan.points} punktów z usługi wysokości GUGiK)."
    )


def fetch_catchment_grid(
    parcel: Parcel, *, max_points: int = CATCHMENT_MAX_POINTS, deadline: float | None = None
) -> tuple[ElevationGrid, str]:
    """Elevation grid over the parcel plus ~300 m with one 10 m step, heights rounded to 0.1 m."""
    plan = catchment_plan(parcel, max_points)
    coarse_points, fine_points = catchment_points(plan)
    heights = sanity.mask_nodata(np.array(_post_heights(coarse_points + fine_points, deadline))).tolist()
    z = assemble_catchment(plan, heights[: len(coarse_points)], heights[len(coarse_points) :])
    if not np.isfinite(z).any():
        raise UpstreamError("height service returned no heights for the margin grid")
    z = np.round(z, 1)
    terrain = grid_stats(z, plan.x0, plan.y_top, CATCHMENT_STEP_M, parcel, "gugik-nmt-points")
    assert terrain.grid is not None
    return terrain.grid, catchment_note(plan)


def _with_catchment(
    parcel: Parcel, result: SourceResult[Terrain], deadline: float | None, max_points: int
) -> SourceResult[Terrain]:
    """Add the margin grid to a terrain result that has none. Never turns a usable result into a failure."""
    terrain = result.data
    if terrain is None or terrain.catchment_grid is not None:
        return result
    if result.status != "ok":
        terrain.catchment_note = "Siatki zlewni nie pobrano: wysokości tylko z modelu 90 m."
        return result
    key = f"{parcel.id}_catchment_p{max_points}"
    hit = cache.get_json("terrain", key)
    if hit is not None:
        grid = from_dict(ElevationGrid, hit["grid"])
        cleaned = sanity.mask_nodata(_grid_array(grid))
        grid.z = [[None if np.isnan(v) else round(float(v), 2) for v in row] for row in cleaned]
        terrain.catchment_grid = grid
        terrain.catchment_note = hit["note"]
        return result
    try:
        cache.require_online("terrain", key)
        grid, note = fetch_catchment_grid(parcel, max_points=max_points, deadline=deadline)
    except (GeodataError, OSError, ValueError) as exc:
        terrain.catchment_note = f"Siatki zlewni nie pobrano: {exc}"
        return result
    terrain.catchment_grid, terrain.catchment_note = grid, note
    cache.put_json("terrain", key, {"grid": asdict(grid), "note": note})
    return result


def fetch_terrain(
    parcel: Parcel,
    *,
    spacing_m: float = 10.0,
    margin_m: float = 50.0,
    max_points: int = MAX_POINTS,
    wcs_timeout: float = 4.0,
    deadline: float | None = None,
    with_catchment: bool = False,
    catchment_max_points: int = CATCHMENT_MAX_POINTS,
) -> SourceResult[Terrain]:
    """Elevation grid over the parcel bbox plus margin, with min / max / mean, slope and the lowest outline point.

    with_catchment: also download `Terrain.catchment_grid` (outline plus ~300 m) for D8 accumulation. Off by
    default: it is several times the points of the main grid and nothing but the D8 variant reads it.
    """
    result = _fetch_main(parcel, spacing_m, margin_m, max_points, wcs_timeout, deadline)
    if with_catchment:
        result = _with_catchment(parcel, result, deadline, catchment_max_points)
    return result


def _fetch_main(
    parcel: Parcel,
    spacing_m: float,
    margin_m: float,
    max_points: int,
    wcs_timeout: float,
    deadline: float | None,
) -> SourceResult[Terrain]:
    key = f"{parcel.id}_s{spacing_m:g}_m{margin_m:g}_p{max_points}"
    hit = cache.get_json("terrain", key)
    if hit is not None and hit["status"] != "ok":
        hit = cache.get_json(
            "terrain", key, config.DAY
        )  # coarse fallback: try the national model again after a day
    if hit is not None:
        try:
            cached, checked = assess_terrain(parcel, from_dict(Terrain, hit["data"]))
        except UpstreamError:
            if config.is_offline():
                raise
            hit = None  # the stored answer is not plausible: download again
        else:
            return SourceResult(
                "terrain", hit["status"], cached, source_url=hit["url"], retrieved_at=hit["retrieved_at"],
                resolution=hit["resolution"], notes=[*hit["notes"], *checked], from_cache=True,
            )  # fmt: skip
    cache.require_online("terrain", key)
    notes: list[str] = []
    status = "ok"
    try:
        terrain, url, extra = _from_points(parcel, spacing_m, margin_m, max_points, deadline)
        resolution = RES_POINTS
        notes += extra
    except CacheMiss:
        raise
    except (GeodataError, OSError, ValueError) as exc:
        notes.append(f"GUGiK height service unavailable: {exc}")
        try:
            terrain, url = _from_wcs(parcel, margin_m, wcs_timeout, deadline)
            resolution = RES_WCS
        except (GeodataError, OSError, ValueError) as exc_wcs:
            notes.append(f"GUGiK NMT WCS unavailable: {exc_wcs}")
            terrain, url = _from_coarse(parcel, margin_m, deadline)
            status, resolution = "fallback", RES_FALLBACK
            notes.append("90 m model: differences inside a small parcel are below its accuracy")
    terrain, checked = assess_terrain(parcel, terrain)
    entry = {
        "status": status, "data": asdict(terrain), "url": url, "retrieved_at": now_iso(), "resolution": resolution,
        "notes": notes,
    }  # fmt: skip
    cache.put_json("terrain", key, entry)
    return SourceResult(
        "terrain", status, terrain, source_url=url, retrieved_at=entry["retrieved_at"], resolution=resolution,
        notes=[*notes, *checked],
    )  # fmt: skip
