"""Elevation of the parcel and its surroundings: grid plus summary statistics.

Provider chain, most useful first:
1. GUGiK height service (GetHByPointList): the national 1 m terrain model sampled on a regular grid.
2. GUGiK NMT through WCS (same model as a raster), when the point service fails.
3. Open-Meteo Elevation API (Copernicus GLO-90, 90 m); status `fallback`.
"""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict

import numpy as np

from . import cache, config, http
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

    z = np.asarray(z, dtype="float64")
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
        mask = valid
    if not mask.any():
        raise UpstreamError("elevation grid has no valid cells")
    slope_mean = slope_max = None
    if min(z.shape) >= 3:
        filled = np.where(valid, z, np.nanmean(z[valid]))
        dy, dx = np.gradient(filled, step)
        slope = np.hypot(dx, dy) * 100.0
        slope_mean, slope_max = round(float(slope[mask].mean()), 2), round(float(slope[mask].max()), 2)
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
        heights = [h for part in pool.map(fetch, chunks) for h in part]
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


def fetch_terrain(
    parcel: Parcel,
    *,
    spacing_m: float = 10.0,
    margin_m: float = 50.0,
    max_points: int = MAX_POINTS,
    wcs_timeout: float = 4.0,
    deadline: float | None = None,
) -> SourceResult[Terrain]:
    """Elevation grid over the parcel bbox plus margin, with min / max / mean, slope and the lowest outline point."""
    key = f"{parcel.id}_s{spacing_m:g}_m{margin_m:g}_p{max_points}"
    hit = cache.get_json("terrain", key)
    if hit is not None and hit["status"] != "ok":
        hit = cache.get_json(
            "terrain", key, config.DAY
        )  # coarse fallback: try the national model again after a day
    if hit is not None:
        return SourceResult(
            "terrain", hit["status"], from_dict(Terrain, hit["data"]), source_url=hit["url"],
            retrieved_at=hit["retrieved_at"], resolution=hit["resolution"], notes=hit["notes"], from_cache=True,
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
    entry = {
        "status": status, "data": asdict(terrain), "url": url, "retrieved_at": now_iso(), "resolution": resolution,
        "notes": notes,
    }  # fmt: skip
    cache.put_json("terrain", key, entry)
    return SourceResult(
        "terrain", status, terrain, source_url=url, retrieved_at=entry["retrieved_at"], resolution=resolution,
        notes=notes,
    )  # fmt: skip
