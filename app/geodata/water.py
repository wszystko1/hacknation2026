"""Ditches, streams, canals and water bodies near the parcel, read from the BDOT10k map service.

The public service draws the topographic database (BDOT10k) as map images and does not hand out
vectors. We request one transparent image per feature kind, treat every drawn pixel as "feature here",
trace the outlines and measure distances from the parcel boundary. Line widths are map symbols.
"""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict

import numpy as np

from . import cache, config, http
from .errors import UpstreamError
from .models import Parcel, SourceResult, Water, WaterFeature, from_dict, now_iso

RESOLUTION = "BDOT10k (1:10 000 topographic database) rendered by the GUGiK map service, read at 2 m pixels"
LAYERS = {
    "ditch": "row",
    "stream": "rz,rzOk",
    "canal": "kan,kanOkr",
    "water_body": "WPow,ZbTA",
}
MAX_SIDE_PX = 2048
MAX_FEATURES = 300
TTL = 90 * config.DAY


def distance_to_ring(points: np.ndarray, ring: list[list[float]]) -> np.ndarray:
    """Shortest distance from each point (n, 2) to the closed polyline `ring`."""
    best = np.full(len(points), np.inf)
    for (xa, ya), (xb, yb) in zip(ring[:-1], ring[1:], strict=True):
        dx, dy = xb - xa, yb - ya
        length2 = dx * dx + dy * dy
        if length2 == 0:
            t = np.zeros(len(points))
        else:
            t = np.clip(((points[:, 0] - xa) * dx + (points[:, 1] - ya) * dy) / length2, 0, 1)
        best = np.minimum(best, np.hypot(points[:, 0] - (xa + t * dx), points[:, 1] - (ya + t * dy)))
    return best


def features_from_mask(
    mask: np.ndarray, kind: str, x0: float, y_top: float, pixel: float, parcel: Parcel, inside: np.ndarray
) -> list[WaterFeature]:
    """Connected groups of drawn pixels as features with outline, drawn area and distance to the parcel."""
    from rasterio.features import shapes
    from rasterio.transform import from_origin

    if not mask.any():
        return []
    transform = from_origin(x0, y_top, pixel, pixel)
    rows, cols = np.nonzero(mask)
    centres = np.column_stack([x0 + (cols + 0.5) * pixel, y_top - (rows + 0.5) * pixel])
    dist = distance_to_ring(centres, parcel.rings_2180[0])
    dist = np.maximum(dist - pixel / 2, 0.0)  # a pixel centre is half a pixel away from the pixel edge
    dist[inside[rows, cols]] = 0.0
    dist_grid = np.full(mask.shape, np.inf)
    dist_grid[rows, cols] = dist
    found = []
    for geometry, _ in shapes(mask.astype("uint8"), mask=mask, transform=transform, connectivity=8):
        ring = geometry["coordinates"][0]
        xs, ys = [p[0] for p in ring], [p[1] for p in ring]
        c0, c1 = int((min(xs) - x0) / pixel), math.ceil((max(xs) - x0) / pixel)
        r0, r1 = int((y_top - max(ys)) / pixel), math.ceil((y_top - min(ys)) / pixel)
        window = dist_grid[r0:r1, c0:c1]
        area = (
            abs(sum(ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1] for i in range(len(ring) - 1)))
            / 2
        )
        found.append(
            WaterFeature(
                kind=kind,
                distance_m=round(float(window.min()), 1),
                area_m2=round(area, 1),
                rings_2180=[[[round(x, 1), round(y, 1)] for x, y in r] for r in geometry["coordinates"]],
            )  # fmt: skip
        )
    return found


def _decode_alpha(png: bytes) -> np.ndarray:
    import warnings

    import rasterio

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # a PNG has no georeferencing; we know the frame we asked for
        with rasterio.MemoryFile(png) as memory, memory.open() as ds:
            return ds.read(ds.count) > 64  # last band is alpha


def fetch_water(
    parcel: Parcel, *, search_m: float = 500.0, pixel_m: float = 2.0, deadline: float | None = None
) -> SourceResult[Water]:
    """Ditches and waters within `search_m` of the parcel bbox and their distance from the parcel boundary."""
    key = f"{parcel.id}_r{search_m:g}_p{pixel_m:g}"
    hit = cache.get_json("water", key, TTL)
    if hit is not None:
        return SourceResult(
            "water", "ok", from_dict(Water, hit["data"]), source_url=hit["url"], retrieved_at=hit["retrieved_at"],
            resolution=RESOLUTION, notes=hit["notes"], from_cache=True,
        )  # fmt: skip
    cache.require_online("water", key)
    from rasterio.features import geometry_mask
    from rasterio.transform import from_origin

    xmin, ymin, xmax, ymax = parcel.bbox_2180
    xmin, ymin, xmax, ymax = xmin - search_m, ymin - search_m, xmax + search_m, ymax + search_m
    pixel = max(pixel_m, max(xmax - xmin, ymax - ymin) / MAX_SIDE_PX)
    width, height = math.ceil((xmax - xmin) / pixel), math.ceil((ymax - ymin) / pixel)
    xmax, ymin = xmin + width * pixel, ymax - height * pixel
    base = {
        "SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetMap", "STYLES": "", "FORMAT": "image/png",
        "TRANSPARENT": "TRUE", "SRS": "EPSG:2180", "BBOX": f"{xmin:.2f},{ymin:.2f},{xmax:.2f},{ymax:.2f}",
        "WIDTH": str(width), "HEIGHT": str(height),
    }  # fmt: skip

    def one(kind: str) -> np.ndarray:
        resp = http.get(
            config.BDOT_WMS_URL,
            params=base | {"LAYERS": LAYERS[kind]},
            timeout=8.0,
            retries=1,
            deadline=deadline,
        )
        if resp.status_code != 200 or resp.content[:4] != b"\x89PNG":
            raise UpstreamError(
                f"BDOT10k map service HTTP {resp.status_code} for {kind}: {resp.content[:100]!r}"
            )
        return _decode_alpha(resp.content)

    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="geodata-water") as pool:
        futures = {kind: pool.submit(one, kind) for kind in LAYERS}
        masks, notes = {}, []
        for kind, future in futures.items():
            try:
                masks[kind] = future.result()
            except UpstreamError as exc:
                notes.append(f"{kind} layer not read: {exc}")
    if not masks:
        raise UpstreamError("; ".join(notes))
    geometry = {"type": "Polygon", "coordinates": [parcel.rings_2180[0]]}
    inside = geometry_mask(
        [geometry], out_shape=(height, width), transform=from_origin(xmin, ymax, pixel, pixel), invert=True
    )
    features: list[WaterFeature] = []
    nearest: dict[str, float | None] = {kind: None for kind in LAYERS}
    for kind, mask in masks.items():
        found = features_from_mask(mask, kind, xmin, ymax, pixel, parcel, inside)
        if found:
            nearest[kind] = min(f.distance_m for f in found)
        features += found
    features.sort(key=lambda f: f.distance_m)
    if len(features) > MAX_FEATURES:
        notes.append(f"{len(features)} features found, the nearest {MAX_FEATURES} returned")
        features = features[:MAX_FEATURES]
    known = {k: v for k, v in nearest.items() if v is not None}
    any_kind = min(known, key=known.get) if known else None
    if pixel > pixel_m:
        notes.append(f"pixel widened to {pixel:.1f} m for a large parcel")
    notes.append(
        f"distances are read from a map image: accuracy about {pixel:.0f}-{2 * pixel:.0f} m; None = nothing within {search_m:.0f} m"
    )
    data = Water(
        provider="gugik-bdot10k-wms", search_m=search_m, pixel_m=round(pixel, 2), features=features,
        nearest_ditch_m=nearest["ditch"], nearest_stream_m=nearest["stream"], nearest_canal_m=nearest["canal"],
        nearest_water_body_m=nearest["water_body"], nearest_any_m=known[any_kind] if any_kind else None,
        nearest_any_kind=any_kind,
    )  # fmt: skip
    status = "ok" if len(masks) == len(LAYERS) else "fallback"
    entry = {"data": asdict(data), "url": config.BDOT_WMS_URL, "retrieved_at": now_iso(), "notes": notes}
    if status == "ok":
        cache.put_json("water", key, entry)
    return SourceResult(
        "water", status, data, source_url=config.BDOT_WMS_URL, retrieved_at=entry["retrieved_at"],
        resolution=RESOLUTION, notes=notes,
    )  # fmt: skip
