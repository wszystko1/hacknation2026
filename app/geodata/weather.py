"""Daily precipitation and FAO-56 reference evapotranspiration for a point, 10+ seasons per request.

Provider chain:
1. Open-Meteo Historical Weather API (ERA5 / ERA5-Land reanalysis) when it answers: both variables.
2. Otherwise station measurements from the IMGW-PIB archive (index built once by `imgw-sync`):
   precipitation from the nearest rain gauges, ET0 computed with FAO-56 Penman-Monteith from the
   nearest synoptic station.
3. NASA POWER (MERRA-2 / CERES) for every day the stations do not cover; ET0 computed here as well.
The newest days, which none of the above has yet, come from the Open-Meteo forecast model.
The result says which provider supplied what share of the days.
"""

from __future__ import annotations

import time
from datetime import date, timedelta

import numpy as np

from . import cache, config, http, imgw
from .errors import CacheMiss, GeodataError, UpstreamError
from .et0 import et0_penman_monteith
from .models import SourceResult, Weather, now_iso

RES_OPEN_METEO = "ERA5-Land ~9 km / ERA5 ~25 km reanalysis grid, daily"
RES_POWER = "NASA POWER: MERRA-2 0.5 x 0.625 deg (~50 km) meteorology, CERES 1 deg radiation, daily"
RES_IMGW = "IMGW-PIB station measurements (rain gauge / synoptic station), daily"
HISTORY_YEARS = 10
IMMUTABLE_AFTER_DAYS = 10  # reanalysis older than this no longer changes for our purposes
RETRY_PRIMARY_S = config.DAY  # without the primary provider the series is rebuilt after a day
MAX_GAUGE_KM = 40.0
MAX_SYNOP_KM = 80.0
ARCHIVE, IMGW, POWER, FORECAST = "open-meteo-archive", "imgw", "nasa-power", "open-meteo-forecast"
SOURCES = ["", ARCHIVE, IMGW, POWER, FORECAST]  # per-day source codes stored with the series

_archive_blocked_until = 0.0  # monotonic time; skip the primary provider after a rate-limit answer


def _iso_range(start: date, end: date) -> list[str]:
    return [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]


def parse_open_meteo(payload: dict) -> dict:
    daily = payload.get("daily") or {}
    if "time" not in daily:
        raise UpstreamError(f"Open-Meteo: {str(payload.get('reason') or payload)[:160]}")
    return {
        "latitude": payload.get("latitude"), "longitude": payload.get("longitude"),
        "dates": daily["time"], "precipitation_mm": daily.get("precipitation_sum"),
        "et0_mm": daily.get("et0_fao_evapotranspiration"),
    }  # fmt: skip


def parse_nasa_power(payload: dict, latitude: float) -> dict:
    try:
        par = payload["properties"]["parameter"]
        coords = payload["geometry"]["coordinates"]
        keys = sorted(par["PRECTOTCORR"])
    except (KeyError, TypeError) as exc:
        raise UpstreamError(f"NASA POWER: unexpected answer: {str(payload)[:160]}") from exc

    def col(name: str) -> np.ndarray:
        arr = np.array([par[name].get(k, -999.0) for k in keys], dtype=float)
        arr[arr <= -900] = np.nan
        return arr

    doy = np.array([date(int(k[:4]), int(k[4:6]), int(k[6:])).timetuple().tm_yday for k in keys], dtype=float)
    elevation = float(coords[2]) if len(coords) > 2 else 100.0
    with np.errstate(invalid="ignore"):
        et0 = et0_penman_monteith(
            col("T2M_MAX"), col("T2M_MIN"), col("RH2M"), col("WS2M"), col("ALLSKY_SFC_SW_DWN"), doy, latitude,
            elevation,
        )  # fmt: skip

    def clean(arr: np.ndarray) -> list[float | None]:
        return [None if np.isnan(v) else round(float(v), 2) for v in arr]

    return {
        "latitude": coords[1], "longitude": coords[0],
        "dates": [f"{k[:4]}-{k[4:6]}-{k[6:]}" for k in keys],
        "precipitation_mm": clean(col("PRECTOTCORR")), "et0_mm": clean(et0),
    }  # fmt: skip


def _fetch_archive(
    lat: float, lon: float, start: date, end: date, deadline: float | None
) -> tuple[dict, str]:
    global _archive_blocked_until
    if config.imgw_only_weather():
        raise UpstreamError("Open-Meteo archive not used: GEODATA_WEATHER=imgw")
    if time.monotonic() < _archive_blocked_until:
        raise UpstreamError("Open-Meteo archive skipped: rate limit reported earlier in this process")
    params = {
        "latitude": lat, "longitude": lon, "start_date": start.isoformat(), "end_date": end.isoformat(),
        "daily": "precipitation_sum,et0_fao_evapotranspiration", "timezone": "Europe/Warsaw",
    }  # fmt: skip
    resp = http.get(
        config.OPEN_METEO_ARCHIVE_URL,
        params=params,
        timeout=config.TIMEOUTS["weather"],
        retries=0,
        deadline=deadline,
    )
    if resp.status_code != 200:
        if resp.status_code == 429 or "limit" in resp.text.lower():
            _archive_blocked_until = time.monotonic() + 600
        raise UpstreamError(f"Open-Meteo archive HTTP {resp.status_code}: {resp.text[:160]}")
    return parse_open_meteo(resp.json()), str(resp.url)


def _fetch_power(lat: float, lon: float, start: date, end: date, deadline: float | None) -> tuple[dict, str]:
    params = {
        "parameters": "PRECTOTCORR,T2M_MAX,T2M_MIN,RH2M,WS2M,ALLSKY_SFC_SW_DWN", "community": "AG",
        "longitude": lon, "latitude": lat, "start": start.strftime("%Y%m%d"), "end": end.strftime("%Y%m%d"),
        "format": "JSON",
    }  # fmt: skip
    resp = http.get(
        config.NASA_POWER_URL, params=params, timeout=config.TIMEOUTS["weather"], retries=1, deadline=deadline
    )
    if resp.status_code != 200:
        raise UpstreamError(f"NASA POWER HTTP {resp.status_code}: {resp.text[:160]}")
    return parse_nasa_power(resp.json(), lat), str(resp.url)


def _overlay(target: list, codes: list[int], values: list, code: int, *, replace: bool) -> int:
    """Copy non-missing `values` into `target`; with replace=False only where target is empty. Returns days set."""
    count = 0
    for i, value in enumerate(values):
        if value is not None and (replace or target[i] is None):
            target[i], codes[i] = value, code
            count += 1
    return count


def _fill_recent(series: dict, lat: float, lon: float, deadline: float | None) -> str:
    """Fill missing days of the last weeks from the Open-Meteo forecast model. Returns a note ("" on success)."""
    dates, prec, et0 = series["dates"], series["precipitation_mm"], series["et0_mm"]
    tail = range(max(0, len(dates) - 92), len(dates))
    if not any(prec[i] is None or et0[i] is None for i in tail):
        return ""
    params = {
        "latitude": lat, "longitude": lon, "past_days": 92, "forecast_days": 1,
        "daily": "precipitation_sum,et0_fao_evapotranspiration", "timezone": "Europe/Warsaw",
    }  # fmt: skip
    try:
        resp = http.get(
            config.OPEN_METEO_FORECAST_URL, params=params, timeout=6.0, retries=0, deadline=deadline
        )
        if resp.status_code != 200:
            raise UpstreamError(f"HTTP {resp.status_code}: {resp.text[:120]}")
        recent = parse_open_meteo(resp.json())
    except GeodataError as exc:
        return f"newest days not filled, forecast model unavailable: {exc}"
    lookup = dict(
        zip(recent["dates"], zip(recent["precipitation_mm"], recent["et0_mm"], strict=True), strict=True)
    )
    first = ""
    for i in tail:
        p, e = lookup.get(dates[i], (None, None))
        used = False
        if prec[i] is None and p is not None:
            prec[i], series["p_src"][i], used = p, SOURCES.index(FORECAST), True
        if et0[i] is None and e is not None:
            et0[i], series["e_src"][i], used = e, SOURCES.index(FORECAST), True
        if used:
            first = first or dates[i]
    series["recent_filled_from"] = first
    return ""


def _attach_temperature_and_sunshine(series: dict, lat: float, lon: float, start: date, today: date) -> None:
    """Daily mean temperature and sunshine from the nearest IMGW synoptic stations, for the second ET variant.

    Read from the local station index (no request); empty lists when the index has none or no station is near.
    """
    tmean = imgw.lookup("tmean", lat, lon, start, today, max_km=MAX_SYNOP_KM, max_stations=2)
    sun = imgw.lookup("sun", lat, lon, start, today, max_km=MAX_SYNOP_KM, max_stations=2)
    if tmean and sun and tmean["stations"] and sun["stations"]:
        series["tmean_c"], series["sunshine_h"] = tmean["values"], sun["values"]


def _download(lat: float, lon: float, start: date, today: date, deadline: float | None) -> dict:
    notes: list[str] = []
    days = _iso_range(start, today)
    n = len(days)
    series: dict = {
        "latitude": lat, "longitude": lon, "dates": days, "precipitation_mm": [None] * n, "et0_mm": [None] * n,
        "p_src": [0] * n, "e_src": [0] * n, "recent_filled_from": "", "stations": {},
    }  # fmt: skip
    urls: list[str] = []

    def place(source: dict, code: int, *, replace: bool) -> None:
        by_day = dict(
            zip(source["dates"], zip(source["precipitation_mm"], source["et0_mm"], strict=True), strict=True)
        )
        _overlay(
            series["precipitation_mm"],
            series["p_src"],
            [by_day.get(d, (None, None))[0] for d in days],
            code,
            replace=replace,
        )
        _overlay(
            series["et0_mm"],
            series["e_src"],
            [by_day.get(d, (None, None))[1] for d in days],
            code,
            replace=replace,
        )

    try:
        gridded, url = _fetch_archive(lat, lon, start, today, deadline)
        place(gridded, SOURCES.index(ARCHIVE), replace=True)
        series["latitude"], series["longitude"] = gridded["latitude"], gridded["longitude"]
        urls.append(url)
        primary = True
    except CacheMiss:
        raise
    except GeodataError as primary_error:
        primary = False
        notes.append(f"Open-Meteo archive not used: {primary_error}")
        gauge = imgw.lookup("precip", lat, lon, start, today, max_km=MAX_GAUGE_KM, max_stations=5)
        synop = imgw.lookup("et0", lat, lon, start, today, max_km=MAX_SYNOP_KM, max_stations=2)
        if imgw.load_index() is None:
            notes.append("IMGW station index not built (run the imgw-sync command once)")
        if gauge and gauge["stations"]:
            _overlay(
                series["precipitation_mm"],
                series["p_src"],
                gauge["values"],
                SOURCES.index(IMGW),
                replace=True,
            )
            series["stations"]["precipitation"] = gauge["stations"]
            urls.append(imgw.BASE_URL)
        elif imgw.load_index() is not None:
            notes.append(f"no IMGW rain gauge with coordinates within {MAX_GAUGE_KM:.0f} km")
        if synop and synop["stations"]:
            _overlay(series["et0_mm"], series["e_src"], synop["values"], SOURCES.index(IMGW), replace=True)
            series["stations"]["et0"] = synop["stations"]
            notes.append(
                "IMGW ET0: FAO-56 Penman-Monteith, radiation from sunshine hours (Angstrom), wind reduced from 10 m to 2 m"
            )
        elif imgw.load_index() is not None:
            notes.append(
                f"no IMGW synoptic station within {MAX_SYNOP_KM:.0f} km: ET0 from the gridded provider"
            )
        try:
            gridded, url = _fetch_power(lat, lon, start, today, deadline)
            place(gridded, SOURCES.index(POWER), replace=False)
            series["latitude"], series["longitude"] = gridded["latitude"], gridded["longitude"]
            urls.append(url)
        except CacheMiss:
            raise
        except GeodataError as power_error:
            notes.append(f"NASA POWER not used: {power_error}")
            if not urls:
                raise UpstreamError("; ".join(notes)) from power_error
    _attach_temperature_and_sunshine(series, lat, lon, start, today)
    note = _fill_recent(series, lat, lon, deadline)
    if note:
        notes.append(note)
    return {
        "primary": primary, "url": urls[0], "urls": urls, "retrieved_at": now_iso(), "stored_ts": time.time(),
        "fetched_day": today.isoformat(), "start": start.isoformat(), "notes": notes, "series": series,
        "imgw_stamp": imgw.index_stamp(),
    }  # fmt: skip


def _entry_valid(entry: dict, target: date, needed_start: date) -> bool:
    if date.fromisoformat(entry["start"]) > needed_start or date.fromisoformat(entry["fetched_day"]) < target:
        return False
    if config.is_offline():
        return True
    age = time.time() - entry["stored_ts"]
    if not entry["primary"] and (age > RETRY_PRIMARY_S or entry.get("imgw_stamp", "") != imgw.index_stamp()):
        return False
    settled = target <= date.fromisoformat(entry["fetched_day"]) - timedelta(days=IMMUTABLE_AFTER_DAYS)
    return settled or age < (config.TTL_WEATHER_RECENT or 0)


def _find_cached(loc: str, target: date, needed_start: date, *, any_age: bool = False) -> dict | None:
    entry = cache.get_json("weather", loc)
    if not entry or "primary" not in entry:
        return None
    covers = (
        date.fromisoformat(entry["start"]) <= needed_start
        and date.fromisoformat(entry["fetched_day"]) >= target
    )
    return entry if (any_age and covers) or _entry_valid(entry, target, needed_start) else None


def _shares(codes: list[int]) -> dict[str, float]:
    total = max(len(codes), 1)
    counts = {SOURCES[c] or "missing": codes.count(c) for c in set(codes)}
    return {k: round(v / total, 4) for k, v in sorted(counts.items(), key=lambda kv: -kv[1])}


def _main_station(stations: list[dict] | None) -> tuple[str, float | None]:
    if not stations:
        return "", None
    best = max(stations, key=lambda s: s["days"])
    return best["name"], best["km"]


def _build(
    entry: dict, target: date, needed_start: date, from_cache: bool, extra: list[str]
) -> SourceResult[Weather]:
    s = entry["series"]
    lo = (needed_start - date.fromisoformat(entry["start"])).days
    hi = (target - date.fromisoformat(entry["start"])).days + 1
    prec, et0 = s["precipitation_mm"][lo:hi], s["et0_mm"][lo:hi]
    p_sources, e_sources = _shares(s["p_src"][lo:hi]), _shares(s["e_src"][lo:hi])
    p_main = next((k for k in p_sources if k != "missing"), "")
    e_main = next((k for k in e_sources if k != "missing"), "")
    filled = s.get("recent_filled_from") or ""
    missing = sum(1 for p, e in zip(prec, et0, strict=True) if p is None or e is None)
    p_station, p_km = _main_station(s["stations"].get("precipitation")) if IMGW in p_sources else ("", None)
    e_station, e_km = _main_station(s["stations"].get("et0")) if IMGW in e_sources else ("", None)
    used = set(p_sources) | set(e_sources)
    grids = [RES_OPEN_METEO] if ARCHIVE in used else []
    grids += [RES_POWER] if POWER in used else []
    data = Weather(
        provider="+".join(dict.fromkeys(k for k in (p_main, e_main) if k)) or "none",
        latitude=s["latitude"], longitude=s["longitude"], dates=s["dates"][lo:hi], precipitation_mm=prec, et0_mm=et0,
        recent_filled_from=filled if filled and filled <= target.isoformat() else "", missing_days=missing,
        missing_share=round(missing / max(len(prec), 1), 4), precipitation_provider=p_main, et0_provider=e_main,
        precipitation_sources=p_sources, et0_sources=e_sources, precipitation_station=p_station,
        tmean_c=s.get("tmean_c", [])[lo:hi], sunshine_h=s.get("sunshine_h", [])[lo:hi],
        precipitation_station_km=p_km, et0_station=e_station, et0_station_km=e_km, grid="; ".join(grids),
    )  # fmt: skip
    notes = list(entry["notes"]) + extra
    if p_station:
        notes.append(f"precipitation: IMGW station {p_station}, {p_km} km from the parcel")
    if e_station:
        notes.append(f"ET0: IMGW synoptic station {e_station}, {e_km} km from the parcel")
    if data.missing_days:
        notes.append(
            f"{data.missing_days} day(s) ({data.missing_share:.1%}) without data in the returned range"
        )
    if data.recent_filled_from:
        notes.append(
            f"days from {data.recent_filled_from} come from the Open-Meteo forecast model, not from measurements"
        )
    resolution = "; ".join(([RES_IMGW] if IMGW in used else []) + grids)
    measured_or_primary = p_main in (ARCHIVE, IMGW)
    return SourceResult(
        "weather", "ok" if measured_or_primary else "fallback", data, source_url=entry["url"],
        retrieved_at=entry["retrieved_at"], resolution=resolution, notes=notes, from_cache=from_cache,
    )  # fmt: skip


def fetch_weather(
    lat: float, lon: float, target: date, *, today: date | None = None, deadline: float | None = None
) -> SourceResult[Weather]:
    """Daily series from 1 January ten years before `target` up to `target` (inclusive).

    One download per location covers every later request date: the series is always fetched up to
    today and sliced. Coordinates are rounded to 0.01 deg (~1 km), far below the model grid.
    Status is `ok` when precipitation comes mostly from Open-Meteo reanalysis or IMGW stations and
    `fallback` when it comes mostly from NASA POWER.
    """
    today = today or date.today()
    if target > today:
        raise GeodataError(f"date {target} is in the future")
    lat_r, lon_r = round(lat, 2), round(lon, 2)
    loc = f"{lat_r:.2f}_{lon_r:.2f}"
    needed_start = date(target.year - HISTORY_YEARS, 1, 1)
    entry = _find_cached(loc, target, needed_start)
    if entry is not None:
        return _build(entry, target, needed_start, True, [])
    try:
        cache.require_online("weather", loc)
        # Fixed start: 1 January twenty years back covers ten seasons before any date of the last ten years.
        entry = _download(
            lat_r, lon_r, min(needed_start, date(today.year - 2 * HISTORY_YEARS, 1, 1)), today, deadline
        )
    except GeodataError as exc:
        stale = _find_cached(loc, target, needed_start, any_age=True)
        if stale is None:
            raise
        return _build(stale, target, needed_start, True, [f"refresh failed, serving older copy: {exc}"])
    cache.put_json("weather", loc, entry)
    return _build(entry, target, needed_start, False, [])
