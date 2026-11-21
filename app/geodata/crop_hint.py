"""Crop seen on the parcel in the JRC EUCROPMAP 2022 classification. A hint, not a declaration."""

from __future__ import annotations

from dataclasses import asdict

import numpy as np

from . import cache, config
from .errors import UpstreamError
from .models import CropClass, CropHint, Parcel, SourceResult, from_dict, now_iso

MAP_YEAR = 2022
RESOLUTION = "JRC EUCROPMAP 2022, 10 m pixels, classified from Sentinel-1/2; one season only"
LEGEND = {
    100: "Artificial", 211: "Common wheat", 212: "Durum wheat", 213: "Barley", 214: "Rye", 215: "Oats",
    216: "Maize", 217: "Rice", 218: "Triticale", 219: "Other cereals", 221: "Potatoes", 222: "Sugar beet",
    223: "Other root crops", 230: "Other non-permanent industrial crops", 231: "Sunflower",
    232: "Rape and turnip rape", 233: "Soya", 240: "Dry pulses", 250: "Fodder crops", 290: "Bare arable land",
    300: "Woodland and shrubland (incl. permanent crops)", 500: "Grasslands", 600: "Bare land", 700: "Water",
    800: "Wetlands",
}  # fmt: skip
GDAL_ENV = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
    "CPL_VSIL_CURL_USE_HEAD": "NO", "GDAL_HTTP_TIMEOUT": "7", "GDAL_HTTP_CONNECTTIMEOUT": "4",
    "GDAL_HTTP_USERAGENT": config.USER_AGENT,
}  # fmt: skip


def class_shares(values: np.ndarray) -> tuple[list[CropClass], int]:
    """Shares of each class among the non-empty pixels, largest first."""
    values = values[values > 0]
    if values.size == 0:
        return [], 0
    codes, counts = np.unique(values, return_counts=True)
    classes = [
        CropClass(int(c), LEGEND.get(int(c), f"class {int(c)}"), round(float(n) / values.size, 3))
        for c, n in zip(codes, counts, strict=True)
    ]
    return sorted(classes, key=lambda c: -c.share), int(values.size)


def fetch_crop_hint(
    parcel: Parcel, *, url: str | None = None, deadline: float | None = None
) -> SourceResult[CropHint]:
    """Class histogram of the map pixels inside the parcel (one windowed range read of a remote GeoTIFF)."""
    key = f"{parcel.id}_{MAP_YEAR}"
    hit = cache.get_json("crop_hint", key)
    source = url or config.EUCROPMAP_URL
    notes = [
        "hint from a 2022 satellite classification; crops rotate, ask the farmer",
        "no winter/spring split of cereals",
    ]
    if hit is not None:
        return SourceResult(
            "crop_hint", "ok", from_dict(CropHint, hit["data"]), source_url=hit["url"],
            retrieved_at=hit["retrieved_at"], resolution=RESOLUTION, notes=notes, from_cache=True,
        )  # fmt: skip
    cache.require_online("crop_hint", key)
    import rasterio
    from pyproj import Transformer
    from rasterio.features import geometry_mask
    from rasterio.windows import from_bounds
    from rasterio.windows import transform as window_transform

    try:
        with rasterio.Env(**GDAL_ENV), rasterio.open(source) as ds:
            tr = Transformer.from_crs(2180, ds.crs, always_xy=True)
            ring = [tr.transform(x, y) for x, y in parcel.rings_2180[0]]
            xs, ys = [p[0] for p in ring], [p[1] for p in ring]
            window = (
                from_bounds(min(xs), min(ys), max(xs), max(ys), ds.transform).round_offsets().round_lengths()
            )
            data = ds.read(1, window=window)
            transform = window_transform(window, ds.transform)
    except rasterio.errors.RasterioError as exc:
        raise UpstreamError(f"EUCROPMAP read failed: {exc}") from exc
    if data.size == 0:
        raise UpstreamError("EUCROPMAP: parcel outside the map")
    geometry = {"type": "Polygon", "coordinates": [ring]}
    mask = geometry_mask([geometry], out_shape=data.shape, transform=transform, invert=True)
    if mask.sum() < 4:
        mask = geometry_mask(
            [geometry], out_shape=data.shape, transform=transform, invert=True, all_touched=True
        )
    classes, pixels = class_shares(data[mask])
    hint = CropHint(
        map_year=MAP_YEAR, classes=classes, dominant=classes[0].name if classes else None, pixels=pixels
    )
    entry = {"data": asdict(hint), "url": source, "retrieved_at": now_iso()}
    cache.put_json("crop_hint", key, entry)
    return SourceResult(
        "crop_hint", "ok" if classes else "fallback", hint, source_url=source, retrieved_at=entry["retrieved_at"],
        resolution=RESOLUTION, notes=notes if classes else [*notes, "no classified pixels inside the parcel"],
    )  # fmt: skip
