"""Outlook sources: short-range forecast (up to 16 days) and the seasonal ensemble (about 6 months)."""

from __future__ import annotations

from dataclasses import asdict

import numpy as np

from . import cache, config, http
from .errors import UpstreamError
from .models import Forecast, Seasonal, SourceResult, now_iso

DAILY = "precipitation_sum,et0_fao_evapotranspiration"
RES_FORECAST = "Open-Meteo best-match weather models, grid 2-25 km, daily; skill drops after about 7 days"
RES_SEASONAL = (
    "ECMWF SEAS5 seasonal ensemble via Open-Meteo, grid ~36 km; a statement about odds, not about single days"
)
TTL = 3 * 3600.0


def fetch_forecast(
    lat: float, lon: float, *, days: int = 16, deadline: float | None = None
) -> SourceResult[Forecast]:
    """Daily precipitation and ET0 for today and the following days (1-16)."""
    key = f"{lat:.2f}_{lon:.2f}_{days}"
    hit = cache.get_json("forecast", key, TTL)
    if hit is None:
        cache.require_online("forecast", key)
        params = {
            "latitude": round(lat, 2), "longitude": round(lon, 2), "forecast_days": days, "daily": DAILY,
            "timezone": "Europe/Warsaw",
        }  # fmt: skip
        resp = http.get(
            config.OPEN_METEO_FORECAST_URL, params=params, timeout=5.0, retries=1, deadline=deadline
        )
        daily = resp.json().get("daily") if resp.status_code == 200 else None
        if not daily or "time" not in daily:
            raise UpstreamError(f"Open-Meteo forecast HTTP {resp.status_code}: {resp.text[:140]}")
        data = Forecast(
            dates=daily["time"], precipitation_mm=daily["precipitation_sum"],
            et0_mm=daily["et0_fao_evapotranspiration"], days=len(daily["time"]),
        )  # fmt: skip
        hit = {"data": asdict(data), "url": str(resp.url), "retrieved_at": now_iso(), "fresh": True}
        cache.put_json("forecast", key, hit | {"fresh": False})
    return SourceResult(
        "forecast", "ok", Forecast(**hit["data"]), source_url=hit["url"], retrieved_at=hit["retrieved_at"],
        resolution=RES_FORECAST, notes=["forecast, not a measurement"], from_cache=not hit.get("fresh", False),
    )  # fmt: skip


def parse_seasonal(payload: dict) -> Seasonal:
    daily = payload.get("daily") or {}
    if "time" not in daily:
        raise UpstreamError(f"Open-Meteo seasonal: {str(payload.get('reason') or payload)[:140]}")

    def members(prefix: str) -> np.ndarray:
        columns = [v for k, v in daily.items() if k.startswith(prefix) and v is not None]
        table = np.array([[np.nan if x is None else x for x in col] for col in columns], dtype="float64")
        return table.reshape(len(columns), len(daily["time"]))

    def clean(values: np.ndarray) -> list[float | None]:
        return [None if np.isnan(v) else round(float(v), 2) for v in values]

    rain, et0 = members("precipitation_sum"), members("et0_fao_evapotranspiration")
    empty = np.full(len(daily["time"]), np.nan)
    with np.errstate(all="ignore"):
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            return Seasonal(
                dates=daily["time"],
                precipitation_mean_mm=clean(np.nanmean(rain, axis=0) if len(rain) else empty),
                precipitation_p10_mm=clean(np.nanpercentile(rain, 10, axis=0) if len(rain) else empty),
                precipitation_p90_mm=clean(np.nanpercentile(rain, 90, axis=0) if len(rain) else empty),
                et0_mean_mm=clean(np.nanmean(et0, axis=0) if len(et0) else empty),
                members=int(len(rain)),
            )


def fetch_seasonal(lat: float, lon: float, *, deadline: float | None = None) -> SourceResult[Seasonal]:
    """Ensemble mean and 10-90 % range of daily precipitation, and mean ET0, for the coming months."""
    key = f"{lat:.1f}_{lon:.1f}"
    hit = cache.get_json("seasonal", key, config.DAY)
    fresh = hit is None
    if hit is None:
        cache.require_online("seasonal", key)
        params = {
            "latitude": round(lat, 1),
            "longitude": round(lon, 1),
            "daily": DAILY,
            "timezone": "Europe/Warsaw",
        }
        resp = http.get(
            config.OPEN_METEO_SEASONAL_URL, params=params, timeout=5.0, retries=1, deadline=deadline
        )
        if resp.status_code != 200:
            raise UpstreamError(f"Open-Meteo seasonal HTTP {resp.status_code}: {resp.text[:140]}")
        hit = {"data": asdict(parse_seasonal(resp.json())), "url": str(resp.url), "retrieved_at": now_iso()}
        cache.put_json("seasonal", key, hit)
    return SourceResult(
        "seasonal", "ok", Seasonal(**hit["data"]), source_url=hit["url"], retrieved_at=hit["retrieved_at"],
        resolution=RES_SEASONAL, notes=["ensemble outlook: use sums over weeks, not single days"], from_cache=not fresh,
    )  # fmt: skip
