"""Orthophoto of the parcel surroundings from the GUGiK WMS, with the outline in pixel coordinates."""

from __future__ import annotations

import math

from . import cache, config, http
from .errors import UpstreamError
from .models import Ortho, Parcel, SourceResult, now_iso

RESOLUTION = "GUGiK orthophoto, source pixel 0.25 m or better, resampled to the requested pixel size"
MAX_SIDE_PX = 2048


def image_frame(
    bbox: list[float], *, margin: float, m_per_px: float | None, max_px: int, min_span_m: float = 120.0
) -> tuple[list[float], int, int, float]:
    """Image bbox, width, height and pixel size for a parcel bbox enlarged by `margin` on each side."""
    xmin, ymin, xmax, ymax = bbox
    cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
    span_x = max((xmax - xmin) * (1 + 2 * margin), min_span_m)
    span_y = max((ymax - ymin) * (1 + 2 * margin), min_span_m)
    pixel = m_per_px if m_per_px else max(span_x, span_y) / max_px
    pixel = max(pixel, max(span_x, span_y) / MAX_SIDE_PX)  # never ask the server for a huge image
    width, height = max(16, math.ceil(span_x / pixel)), max(16, math.ceil(span_y / pixel))
    half_x, half_y = width * pixel / 2, height * pixel / 2
    return [cx - half_x, cy - half_y, cx + half_x, cy + half_y], width, height, pixel


def to_pixels(rings: list[list[list[float]]], frame: list[float], pixel: float) -> list[list[list[float]]]:
    """EPSG:2180 rings -> [col, row] with the origin in the top-left corner of the image."""
    x0, _, _, y1 = frame
    return [[[round((x - x0) / pixel, 1), round((y1 - y) / pixel, 1)] for x, y in ring] for ring in rings]


def fetch_ortho(
    parcel: Parcel,
    *,
    m_per_px: float | None = None,
    margin: float = 0.35,
    max_px: int = 1024,
    deadline: float | None = None,
) -> SourceResult[Ortho]:
    """JPEG orthophoto. With m_per_px=None the longer side of the image has `max_px` pixels."""
    frame, width, height, pixel = image_frame(
        parcel.bbox_2180, margin=margin, m_per_px=m_per_px, max_px=max_px
    )
    key = f"{parcel.id}_{width}x{height}_{pixel:.4f}_{margin:.2f}"
    params = {
        "SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetMap", "LAYERS": "Raster", "STYLES": "",
        "FORMAT": "image/jpeg", "SRS": "EPSG:2180", "BBOX": ",".join(f"{v:.2f}" for v in frame),
        "WIDTH": str(width), "HEIGHT": str(height),
    }  # fmt: skip
    meta = cache.get_json("ortho", key, config.TTL_ORTHO)
    image = cache.get_bytes("ortho", key, config.TTL_ORTHO, ".jpg") if meta else None
    from_cache = image is not None
    if image is None:
        cache.require_online("ortho", key)
        resp = http.get(
            config.ORTHO_WMS_URL, params=params, timeout=config.TIMEOUTS["ortho"], deadline=deadline
        )
        if resp.status_code != 200 or not resp.content.startswith(b"\xff\xd8"):
            raise UpstreamError(f"orthophoto WMS HTTP {resp.status_code}: {resp.content[:120]!r}")
        image = resp.content
        meta = {"url": str(resp.url), "retrieved_at": now_iso()}
        cache.put_bytes("ortho", key, image, ".jpg")
        cache.put_json("ortho", key, meta)
    data = Ortho(
        image=image, content_type="image/jpeg", width=width, height=height, bbox_2180=[round(v, 2) for v in frame],
        m_per_px=round(pixel, 4), polygon_px=to_pixels(parcel.rings_2180, frame, pixel),
    )  # fmt: skip
    return SourceResult(
        "ortho", "ok", data, source_url=meta["url"], retrieved_at=meta["retrieved_at"], resolution=RESOLUTION,
        notes=[f"image pixel {pixel:.2f} m"], from_cache=from_cache,
    )  # fmt: skip
