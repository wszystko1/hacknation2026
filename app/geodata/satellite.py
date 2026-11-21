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
INNER_BUFFER_M = (
    10  # the outline is shrunk by this much before pixels are counted: edge pixels mix in the neighbours
)
MIN_CLEAR_SHARE = (
    0.5  # a scene with a smaller share of clear SCL pixels inside the outline is dropped, with the reason
)
BASELINE_WITH_OFFSET = (
    "04.00"  # from this processing baseline (25.01.2022) ESA adds 1000 to every digital number
)
SEASON_STEP_DAYS = 10  # one reading per this many days, March to September
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
    lon: float, lat: float, center: date, window_days: int, deadline: float | None = None, limit: int = 50
) -> list[dict]:
    """STAC items within +-window_days of `center`, nearest date first (then lower cloud cover)."""
    start, end = center - timedelta(days=window_days), center + timedelta(days=window_days)
    body = {
        "collections": ["sentinel-2-l2a"],
        "intersects": {"type": "Point", "coordinates": [lon, lat]},
        "datetime": f"{start.isoformat()}T00:00:00Z/{end.isoformat()}T23:59:59Z",
        "query": {"eo:cloud_cover": {"lt": MAX_TILE_CLOUD}},
        "limit": limit,
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
    return _one_per_acquisition(items)


def _one_per_acquisition(items: list[dict]) -> list[dict]:
    """The catalogue lists a scene once per reprocessing (id ends with the processing time); keep the first of each."""
    seen: set[str] = set()
    unique = []
    for item in items:
        acquisition = str(item["id"]).rsplit("_", 1)[0]
        if acquisition not in seen:
            seen.add(acquisition)
            unique.append(item)
    return unique


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
    needs_offset = baseline >= BASELINE_WITH_OFFSET and not props.get("earthsearch:boa_offset_applied", False)
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
    key = f"{parcel.id}_{item['id']}_b{INNER_BUFFER_M}"
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
        inner = mask & (_edge_distance(ring, shape, transform) >= INNER_BUFFER_M)
        if inner.sum() >= 4:
            return inner
        if mask.sum() < 4:  # tiny parcel (or one narrower than the buffer): count every touched pixel
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

    def pixel_index(a: np.ndarray, b: np.ndarray, mask: np.ndarray) -> np.ndarray:
        if not mask.any():
            return np.empty(0, dtype="float32")
        a, b = reflectance(a)[mask], reflectance(b)[mask]
        total = a + b
        ok = total > 0
        return (a[ok] - b[ok]) / total[ok]

    def mean_index(a: np.ndarray, b: np.ndarray, mask: np.ndarray) -> float | None:
        values = pixel_index(a, b, mask)
        return round(float(np.mean(values)), 4) if values.size else None

    ndvi_pixels = pixel_index(nir, red, clear10)
    spread = None
    if ndvi_pixels.size >= 4:
        p10, p90 = np.percentile(ndvi_pixels, [10, 90])
        spread = round(float(p90 - p10), 4)

    index = SceneIndex(
        scene_id=item["id"], date=item["date"], days_from_target=(date.fromisoformat(item["date"]) - target).days,
        cloud_cover_pct=None if item["cloud"] is None else round(float(item["cloud"]), 1),
        ndvi=mean_index(nir, red, clear10), ndvi_spread=spread, ndmi=mean_index(nir08, swir, clear20),
        valid_fraction=round(float(clear20.sum()) / max(int(in20.sum()), 1), 3), pixels=int(in10.sum()),
    )  # fmt: skip
    cache.put_json("satellite_scene", key, asdict(index))
    return index


def _edge_distance(ring: list[tuple[float, float]], shape: tuple[int, int], transform) -> np.ndarray:
    """Distance in metres from each pixel centre to the nearest edge of the outline (scene CRS, metric)."""
    rows, cols = np.indices(shape)
    px = transform.c + (cols + 0.5) * transform.a + (rows + 0.5) * transform.b
    py = transform.f + (cols + 0.5) * transform.d + (rows + 0.5) * transform.e
    best = np.full(shape, np.inf)
    for (x0, y0), (x1, y1) in zip(ring, ring[1:], strict=False):
        dx, dy = x1 - x0, y1 - y0
        length2 = dx * dx + dy * dy
        t = np.clip(((px - x0) * dx + (py - y0) * dy) / length2, 0.0, 1.0) if length2 else 0.0
        best = np.minimum(best, np.hypot(px - (x0 + t * dx), py - (y0 + t * dy)))
    return best


def _best_scene(
    items: list[dict],
    parcel: Parcel,
    target: date,
    pool: ThreadPoolExecutor,
    deadline: float | None,
    tries: int = 4,
) -> SceneIndex | None:
    """First of the nearest scenes with at least MIN_CLEAR_SHARE of the shrunken outline cloud-free."""
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
        if index.ndvi is not None and index.valid_fraction >= MIN_CLEAR_SHARE:
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
    key = f"{parcel.id}_{target.isoformat()}_w{window_days}_h{history_years}_{history_window_days}_b{INNER_BUFFER_M}"
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
    dropped = None
    if current is not None and current.valid_fraction < MIN_CLEAR_SHARE:
        dropped, current = current, None  # the scene stays out of the data and the notes say why
    if current is None and not history:
        if dropped is not None:
            notes.append(
                f"dropped: only {dropped.valid_fraction:.0%} of the parcel is cloud-free in the nearest scene "
                f"(at least {MIN_CLEAR_SHARE:.0%} needed)"
            )
        elif current_future.done() and candidates == 0:
            notes.append(f"no scene with tile cloud cover < {MAX_TILE_CLOUD:.0f}% within {window_days} days")
        else:
            notes.append("no cloud-free view of the parcel in the nearest scenes")
    elif current is None:
        if dropped is not None:
            notes.append(
                f"dropped: only {dropped.valid_fraction:.0%} of the parcel is cloud-free in the nearest scene "
                f"(at least {MIN_CLEAR_SHARE:.0%} needed)"
            )
        else:
            notes.append(f"no usable scene within {window_days} days of the requested date")
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


def fetch_season(
    parcel: Parcel, year: int, until: date | None = None, deadline: float | None = None
) -> list[SceneIndex]:
    """Readings of one season (March-September, one per SEASON_STEP_DAYS days), cut at `until`.

    The catalogue is searched in three two-month windows; in each ten-day bin the scene with the least
    cloud on the tile is read first and the next ones only when it is not clear enough. Bins that fail are
    left out: the season is as complete as the sky allowed.
    """
    lon, lat = parcel.centroid_4326
    first, last = date(year, 3, 1), min(until or date(year, 9, 30), date(year, 9, 30))
    items: list[dict] = []
    for start in (date(year, 3, 1), date(year, 5, 1), date(year, 7, 1), date(year, 9, 1)):
        end = min(start + timedelta(days=60), date(year, 9, 30))
        if start > last:
            break
        middle = start + (end - start) / 2
        items += search_scenes(lon, lat, middle, (end - start).days // 2 + 1, deadline, limit=100)
    items = [i for i in _one_per_acquisition(items) if first <= date.fromisoformat(i["date"]) <= last]
    bins: dict[int, list[dict]] = {}
    for item in items:
        offset = (date.fromisoformat(item["date"]) - first).days // SEASON_STEP_DAYS
        bins.setdefault(offset, []).append(item)
    for group in bins.values():
        group.sort(key=lambda i: i["cloud"] or 0.0)
    readings: list[SceneIndex] = []
    band_pool = ThreadPoolExecutor(max_workers=16, thread_name_prefix="geodata-s2-band")
    try:
        with ThreadPoolExecutor(max_workers=6, thread_name_prefix="geodata-s2-season") as pool:
            futures = [
                pool.submit(_best_scene, group, parcel, first, band_pool, deadline, 2)
                for group in bins.values()
            ]
            for future in futures:
                try:
                    reading = future.result()
                except GeodataError:
                    raise
                except Exception:  # noqa: BLE001 - one broken bin must not lose the season
                    continue
                if reading is not None:
                    readings.append(reading)
    finally:
        band_pool.shutdown(wait=False, cancel_futures=True)
    readings.sort(key=lambda r: r.date)
    return readings
