"""Sentinel-2 L2A vegetation (NDVI) and moisture (NDMI) indices for the parcel, from public COGs.

Scenes are found in a public STAC catalogue (Planetary Computer by default, Earth Search as an option); only the parcel window of each band is read.
Clouds, shadows, snow and missing data are removed with the scene classification band (SCL).
This source is optional: callers give it a deadline and use whatever finished in time.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import asdict
from datetime import date, timedelta

import numpy as np

from . import cache, config, http
from .errors import GeodataError, UpstreamError
from .models import Parcel, Satellite, SceneIndex, SourceResult, now_iso

RESOLUTION = "Sentinel-2 L2A: 10 m (NDVI), 20 m (NDMI, cloud mask); revisit 2-5 days, clouds permitting"
ARCHIVE_START = date(2016, 11, 2)  # first L2A scene over Poland in Earth Search
VALID_SCL = (4, 5, 6, 7)  # vegetation, bare soil, water, unclassified
MAX_TILE_CLOUD = 70.0
GDAL_ENV = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
    "GDAL_HTTP_TIMEOUT": "8",
    "GDAL_HTTP_CONNECTTIMEOUT": "4",
    "GDAL_HTTP_MAX_RETRY": "1",
    "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
    "GDAL_HTTP_USERAGENT": config.USER_AGENT,
    "AWS_NO_SIGN_REQUEST": "YES",
    "VSI_CACHE": "TRUE",
}


def search_scenes(
    lon: float, lat: float, center: date, window_days: int, deadline: float | None = None
) -> list[dict]:
    """STAC items within +-window_days of `center`, nearest date first (then lower cloud cover)."""
    start, end = center - timedelta(days=window_days), center + timedelta(days=window_days)
    body = {
        "collections": ["sentinel-2-l2a"],
        "intersects": {"type": "Point", "coordinates": [lon, lat]},
        "datetime": f"{start.isoformat()}T00:00:00Z/{end.isoformat()}T23:59:59Z",
        "query": {"eo:cloud_cover": {"lt": MAX_TILE_CLOUD}},
        "limit": 50,
    }
    resp = http.request(
        "POST", config.stac_search_url(), json=body, timeout=8.0, retries=1, deadline=deadline
    )
    if resp.status_code != 200:
        raise UpstreamError(f"STAC HTTP {resp.status_code}: {resp.text[:160]}")
    token = _sas_token(deadline) if config.stac_provider() == "planetary-computer" else ""
    items = [simplify_item(f, token) for f in resp.json().get("features", [])]
    items = [i for i in items if i is not None]
    # Nearest first, but a cloudy tile is pushed back: 10 points of cloud cover count like 2 days.
    items.sort(key=lambda i: abs((date.fromisoformat(i["date"]) - center).days) + 0.2 * (i["cloud"] or 0.0))
    return items


_token: dict = {"value": "", "expires": 0.0}
_ASSET_NAMES = (
    {"red": "red", "nir": "nir", "nir08": "nir08", "swir16": "swir16", "scl": "scl"},  # Earth Search
    {"red": "B04", "nir": "B08", "nir08": "B8A", "swir16": "B11", "scl": "SCL"},  # Planetary Computer
)


def _sas_token(deadline: float | None = None) -> str:
    """Anonymous read token for the Planetary Computer blobs (no account, valid about an hour)."""
    if time.time() < _token["expires"]:
        return _token["value"]
    resp = http.get(config.PC_TOKEN_URL, timeout=5.0, retries=1, deadline=deadline)
    if resp.status_code != 200 or "token" not in resp.text:
        raise UpstreamError(f"Planetary Computer token HTTP {resp.status_code}")
    _token.update(value=resp.json()["token"], expires=time.time() + 30 * 60)
    return _token["value"]


def simplify_item(feature: dict, token: str = "") -> dict | None:
    """Keep only what the reader needs from a STAC item (Earth Search or Planetary Computer naming)."""
    props, assets = feature.get("properties", {}), feature.get("assets", {})
    names = next((n for n in _ASSET_NAMES if all(v in assets for v in n.values())), None)
    if names is None or not props.get("datetime"):
        return None
    epsg = props.get("proj:epsg") or str(props.get("proj:code", "")).replace("EPSG:", "")
    baseline = str(props.get("s2:processing_baseline", "0"))
    # From baseline 04.00 ESA adds 1000 to every digital number. Earth Search marks scenes whose COGs
    # already had it removed; for the others it has to be subtracted here.
    needs_offset = baseline >= "04.00" and not props.get("earthsearch:boa_offset_applied", False)
    return {
        "id": feature.get("id"), "date": props["datetime"][:10], "cloud": props.get("eo:cloud_cover"),
        "epsg": int(epsg) if epsg else None, "dn_offset": -1000.0 if needs_offset else 0.0,
        "hrefs": {k: assets[v]["href"] + (f"?{token}" if token else "") for k, v in names.items()},
    }  # fmt: skip


def _read_window(href: str, bounds: tuple[float, float, float, float], shape: tuple[int, int] | None):
    """Read the band window covering `bounds` (scene CRS). Returns (array, affine transform)."""
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.windows import from_bounds
    from rasterio.windows import transform as window_transform

    with rasterio.Env(**GDAL_ENV), rasterio.open(href) as ds:
        window = from_bounds(*bounds, transform=ds.transform).round_offsets().round_lengths()
        window = window.intersection(rasterio.windows.Window(0, 0, ds.width, ds.height))
        if shape is None:
            data = ds.read(1, window=window)
        else:
            data = ds.read(1, window=window, out_shape=shape, resampling=Resampling.nearest)
        return data, window_transform(window, ds.transform)


def scene_index(
    item: dict, parcel: Parcel, target: date, pool: ThreadPoolExecutor | None = None
) -> SceneIndex:
    """Parcel-mean NDVI and NDMI of one scene (cached forever per parcel and scene)."""
    key = f"{parcel.id}_{item['id']}"
    hit = cache.get_json("satellite_scene", key)
    if hit is not None:
        return SceneIndex(**(hit | {"days_from_target": (date.fromisoformat(hit["date"]) - target).days}))
    cache.require_online("satellite_scene", key)
    from pyproj import Transformer
    from rasterio.features import geometry_mask

    tr = Transformer.from_crs(2180, item["epsg"], always_xy=True)
    ring = [tr.transform(x, y) for x, y in parcel.rings_2180[0]]
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    bounds = (min(xs) - 20, min(ys) - 20, max(xs) + 20, max(ys) + 20)
    geometry = {"type": "Polygon", "coordinates": [ring]}
    hrefs = item["hrefs"]

    def read(name: str, shape=None):
        return _read_window(hrefs[name], bounds, shape)

    if pool is None:
        red, t10 = read("red")
        jobs = {n: read(n, red.shape if n == "nir" else None) for n in ("nir", "nir08", "swir16", "scl")}
    else:
        first = pool.submit(read, "red")
        others = {n: pool.submit(read, n) for n in ("nir08", "swir16", "scl")}
        red, t10 = first.result()
        nir_future = pool.submit(read, "nir", red.shape)
        jobs = {n: f.result() for n, f in others.items()} | {"nir": nir_future.result()}
    nir = jobs["nir"][0]
    nir08, t20 = jobs["nir08"]
    swir, scl = jobs["swir16"][0], jobs["scl"][0]
    rows, cols = (
        min(nir08.shape[0], swir.shape[0], scl.shape[0]),
        min(nir08.shape[1], swir.shape[1], scl.shape[1]),
    )
    nir08, swir, scl = nir08[:rows, :cols], swir[:rows, :cols], scl[:rows, :cols]

    def inside(shape: tuple[int, int], transform) -> np.ndarray:
        if 0 in shape:
            return np.zeros(shape, dtype=bool)
        mask = geometry_mask([geometry], out_shape=shape, transform=transform, invert=True)
        if mask.sum() < 4:  # tiny parcel: count every touched pixel
            mask = geometry_mask(
                [geometry], out_shape=shape, transform=transform, invert=True, all_touched=True
            )
        return mask

    def reflectance(band: np.ndarray) -> np.ndarray:
        return (band.astype("float32") + item["dn_offset"]) * 1e-4

    in20 = inside(scl.shape, t20)
    clear20 = in20 & np.isin(scl, VALID_SCL) & (nir08 > 0) & (swir > 0)
    # Cloud mask on the 10 m grid: each 10 m pixel takes the class of the 20 m pixel it lies in.
    rr = np.minimum((np.arange(red.shape[0]) // 2), max(scl.shape[0] - 1, 0))
    cc = np.minimum((np.arange(red.shape[1]) // 2), max(scl.shape[1] - 1, 0))
    scl10 = scl[np.ix_(rr, cc)] if scl.size and red.size else np.zeros(red.shape, dtype=scl.dtype)
    in10 = inside(red.shape, t10)
    nir = nir[: red.shape[0], : red.shape[1]]
    clear10 = in10 & np.isin(scl10, VALID_SCL) & (red > 0) & (nir > 0)

    def mean_index(a: np.ndarray, b: np.ndarray, mask: np.ndarray) -> float | None:
        if not mask.any():
            return None
        a, b = reflectance(a)[mask], reflectance(b)[mask]
        total = a + b
        ok = total > 0
        return round(float(np.mean((a[ok] - b[ok]) / total[ok])), 4) if ok.any() else None

    index = SceneIndex(
        scene_id=item["id"], date=item["date"], days_from_target=(date.fromisoformat(item["date"]) - target).days,
        cloud_cover_pct=None if item["cloud"] is None else round(float(item["cloud"]), 1),
        ndvi=mean_index(nir, red, clear10), ndmi=mean_index(nir08, swir, clear20),
        valid_fraction=round(float(clear20.sum()) / max(int(in20.sum()), 1), 3), pixels=int(in10.sum()),
    )  # fmt: skip
    cache.put_json("satellite_scene", key, asdict(index))
    return index


def _best_scene(
    items: list[dict],
    parcel: Parcel,
    target: date,
    pool: ThreadPoolExecutor,
    deadline: float | None,
    tries: int = 4,
) -> SceneIndex | None:
    """First of the nearest scenes in which at least half of the parcel is cloud-free."""
    best: SceneIndex | None = None
    for item in items[:tries]:
        if deadline is not None and time.monotonic() > deadline:
            break
        try:
            index = scene_index(item, parcel, target, pool)
        except GeodataError:
            raise
        except Exception:  # noqa: BLE001 - a broken scene must not hide the next candidate
            continue
        if index.ndvi is not None and index.valid_fraction >= 0.5:
            return index
        if index.ndvi is not None and (best is None or index.valid_fraction > best.valid_fraction):
            best = index
    return best


def _same_day(target: date, year: int) -> date:
    try:
        return target.replace(year=year)
    except ValueError:  # 29 February
        return target.replace(year=year, day=28)


def fetch_satellite(
    parcel: Parcel,
    target: date,
    *,
    window_days: int = 20,
    history_years: int = 3,
    history_window_days: int = 10,
    today: date | None = None,
    deadline: float | None = None,
) -> SourceResult[Satellite]:
    """Nearest usable scene to `target` plus the same time of year in up to `history_years` earlier years.

    Returns status `skipped` for dates before the archive starts, and a partial history (with a note)
    when the deadline arrives first. Raises GeodataError when nothing could be computed.
    """
    today = today or date.today()
    if target + timedelta(days=window_days) < ARCHIVE_START:
        return SourceResult(
            "satellite", "skipped", None, source_url=config.stac_search_url(), retrieved_at=now_iso(),
            resolution=RESOLUTION, notes=[f"no Sentinel-2 L2A scenes before {ARCHIVE_START.isoformat()}"],
        )  # fmt: skip
    key = f"{parcel.id}_{target.isoformat()}_w{window_days}_h{history_years}_{history_window_days}"
    settled = target + timedelta(days=window_days + 5) < today
    hit = cache.get_json("satellite", key, None if settled else config.TTL_SATELLITE_RECENT)
    if hit is not None:
        data = Satellite(
            target_date=hit["data"]["target_date"], candidates=hit["data"]["candidates"],
            current=SceneIndex(**hit["data"]["current"]) if hit["data"]["current"] else None,
            history=[SceneIndex(**h) for h in hit["data"]["history"]],
        )  # fmt: skip
        return SourceResult(
            "satellite", hit["status"], data, source_url=config.stac_search_url(), retrieved_at=hit["retrieved_at"],
            resolution=RESOLUTION, notes=hit["notes"], from_cache=True,
        )  # fmt: skip
    cache.require_online("satellite", key)
    lon, lat = parcel.centroid_4326
    years = [
        y
        for y in range(target.year - 1, target.year - history_years - 1, -1)
        if _same_day(target, y) >= ARCHIVE_START
    ]
    pool = ThreadPoolExecutor(max_workers=16, thread_name_prefix="geodata-s2")
    band_pool = ThreadPoolExecutor(max_workers=16, thread_name_prefix="geodata-s2-band")
    try:

        def one(center: date, window: int) -> tuple[SceneIndex | None, int]:
            items = search_scenes(lon, lat, center, window, deadline)
            return _best_scene(items, parcel, center, band_pool, deadline), len(items)

        current_future = pool.submit(one, target, window_days)
        history_futures = {y: pool.submit(one, _same_day(target, y), history_window_days) for y in years}
        left = None if deadline is None else max(0.0, deadline - time.monotonic() - 0.4)
        wait([current_future, *history_futures.values()], timeout=left)
        notes: list[str] = []
        current, candidates = None, 0
        if current_future.done():
            current, candidates = current_future.result()  # raises the search/read error, if any
        else:
            notes.append("scene for the requested date not ready before the deadline")
        history, unfinished = [], 0
        for year, future in history_futures.items():
            if not future.done():
                unfinished += 1
            elif future.exception() is None and future.result()[0] is not None:
                history.append(future.result()[0])
            elif future.exception() is not None:
                notes.append(f"{year}: {future.exception()}")
        if unfinished:
            notes.append(
                f"history incomplete: {unfinished} of {len(years)} year(s) not ready before the deadline"
            )
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
        band_pool.shutdown(wait=False, cancel_futures=True)
    if current is None and not history:
        if current_future.done() and candidates == 0:
            notes.append(f"no scene with tile cloud cover < {MAX_TILE_CLOUD:.0f}% within {window_days} days")
        else:
            notes.append("no cloud-free view of the parcel in the nearest scenes")
    elif current is None:
        notes.append(f"no usable scene within {window_days} days of the requested date")
    elif current.valid_fraction < 0.5:
        notes.append(f"only {current.valid_fraction:.0%} of the parcel is cloud-free in the nearest scene")
    if current is not None:
        notes.append(f"nearest scene is {abs(current.days_from_target)} day(s) from the requested date")
    data = Satellite(target_date=target.isoformat(), current=current, history=history, candidates=candidates)
    complete = current_future.done() and not unfinished
    status = "ok" if current is not None and complete else "fallback"
    retrieved = now_iso()
    if complete:
        cache.put_json(
            "satellite",
            key,
            {"data": asdict(data), "status": status, "notes": notes, "retrieved_at": retrieved},
        )
    return SourceResult(
        "satellite", status, data, source_url=config.stac_search_url(), retrieved_at=retrieved, resolution=RESOLUTION,
        notes=notes,
    )  # fmt: skip
