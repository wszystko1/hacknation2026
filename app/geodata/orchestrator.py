"""fetch_all: parcel first, then every other source in parallel, within per-source and total time limits."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import date
from typing import Any

from . import config, sanity
from .crop_hint import fetch_crop_hint
from .errors import CacheMiss, InvalidParcelId
from .forecast import fetch_forecast, fetch_seasonal
from .models import FetchResult, SourceResult, now_iso
from .ortho import fetch_ortho
from .parcel import fetch_parcel, fetch_parcel_by_lonlat, normalize_parcel_id
from .satellite import fetch_satellite
from .soil import fetch_soil
from .terrain import CATCHMENT_BUDGET_S, fetch_terrain
from .water import fetch_water
from .weather import fetch_weather

ALL_SOURCES = (
    "parcel", "weather", "ortho", "soil", "satellite", "terrain", "water", "forecast", "seasonal", "crop_hint",
)  # fmt: skip
CORE_SOURCES = ("parcel", "weather")
# Fetched when `sources` is not given. The 183-day seasonal outlook is not part of the report and the crop
# hint (a 6.8 GiB map read through a window) is cut, so both stay available as functions but are not called.
DEFAULT_SOURCES = tuple(n for n in ALL_SOURCES if n not in ("seasonal", "crop_hint"))
DEFAULT_URLS = {
    "parcel": config.ULDK_URL, "weather": config.OPEN_METEO_ARCHIVE_URL, "ortho": config.ORTHO_WMS_URL,
    "soil": config.SOILGRIDS_URL, "satellite": config.stac_search_url(), "terrain": config.NMT_POINTS_URL,
    "water": config.BDOT_WMS_URL, "forecast": config.OPEN_METEO_FORECAST_URL,
    "seasonal": config.OPEN_METEO_SEASONAL_URL, "crop_hint": config.EUCROPMAP_URL,
}  # fmt: skip


class _Task:
    """One source running in a daemon thread, so a hung request can never block the caller or the exit."""

    def __init__(self, name: str, fn: Callable[[], SourceResult[Any]]):
        self.name, self.fn = name, fn
        self.result: SourceResult[Any] | None = None
        self.error: BaseException | None = None
        self.started = time.monotonic()
        self.elapsed_ms = 0
        self.thread = threading.Thread(target=self._run, name=f"geodata-{name}", daemon=True)
        self.thread.start()

    def _run(self) -> None:
        try:
            self.result = self.fn()
        except BaseException as exc:  # noqa: BLE001 - reported as the source status
            self.error = exc
        self.elapsed_ms = int((time.monotonic() - self.started) * 1000)

    def collect(self, deadline: float) -> SourceResult[Any]:
        self.thread.join(max(0.0, deadline - time.monotonic()))
        if self.thread.is_alive():
            limit = deadline - self.started
            return _empty(self.name, "timeout", int(limit * 1000), f"no answer within {limit:.1f} s")
        if self.error is not None:
            if isinstance(self.error, CacheMiss):
                status = "error" if self.name in CORE_SOURCES else "skipped"
                return _empty(
                    self.name, status, self.elapsed_ms, str(self.error), note="offline: not in cache"
                )
            return _empty(self.name, "error", self.elapsed_ms, f"{type(self.error).__name__}: {self.error}")
        assert self.result is not None
        self.result.elapsed_ms = self.elapsed_ms
        return self.result


def _empty(name: str, status: str, elapsed_ms: int, error: str = "", note: str = "") -> SourceResult[Any]:
    return SourceResult(
        name, status, None, elapsed_ms=elapsed_ms, source_url=DEFAULT_URLS[name], retrieved_at=now_iso(),  # type: ignore[arg-type]
        notes=[note] if note else [], error=error,
    )  # fmt: skip


def _vet_parcel(result: SourceResult[Any]) -> SourceResult[Any]:
    """An outline that is not a plausible polygon in Poland is no outline: the source becomes an error with the reason."""
    if not result.usable:
        return result
    parcel = result.data
    verdict = sanity.guarded("obrys działki", sanity.check_outline, parcel.rings_2180, parcel.area_ha)
    if verdict.usable:
        if verdict.note:
            result.notes.append(verdict.note)
        return result
    failed = _empty("parcel", "error", result.elapsed_ms, verdict.missing_text)
    failed.notes = [*result.notes, verdict.missing_text]
    return failed


def d8_wins() -> bool:
    """True when the D8 variant won the placement check, so the margin grid is worth downloading."""
    try:
        from app.advice import placement

        return "d8" in (placement.outlet_method(), placement.basin_method())
    except Exception:  # noqa: BLE001 - no module or no metrics: the base layout needs no margin grid
        return False


def fetch_all(
    parcel_id: str | None,
    date: date | str,  # noqa: A002 - public parameter name
    *,
    budget_s: float = 25.0,
    lonlat: tuple[float, float] | None = None,
    sources: tuple[str, ...] | None = None,
    offline: bool | None = None,
    ortho_m_per_px: float | None = None,
    ortho_max_px: int = 1024,
    history_years: int = 3,
    background: tuple[str, ...] = (),
    with_catchment: bool | None = None,
) -> FetchResult:
    """Fetch everything known about a parcel for a date. Never raises for data or network problems.

    parcel_id: cadastral identifier, e.g. "040303_2.0004.121/7" (or None with `lonlat=(lon, lat)`).
    date: day of the analysis (datetime.date or "YYYY-MM-DD"), today or earlier.
    budget_s: total wall-clock limit; sources still running at that moment get status `timeout`
        (their downloads finish in the background and land in the cache for the next call).
    sources: subset of ALL_SOURCES to run (default DEFAULT_SOURCES); the rest get status `skipped`. Parcel always runs.
    background: sources that do not hold the answer back: after the others have answered they get
        BACKGROUND_GRACE_S more seconds; if still running they report `timeout` and finish up to
        BACKGROUND_S in a daemon thread, so the next call finds them in the cache.
    with_catchment: download the terrain margin grid (None = always for a full report, i.e. without `sources`;
        for a chosen subset only when the D8 variant won the check). It runs inside the report's time limit; when it
        cannot be had, `Terrain.catchment_note` says why.
    offline: serve only from the cache (None = follow GEODATA_OFFLINE).
    Raises only InvalidParcelId / ValueError for malformed input.
    """
    from datetime import date as _date

    started = time.monotonic()
    total_deadline = started + budget_s
    target = _date.fromisoformat(date) if isinstance(date, str) else date
    if parcel_id is None and lonlat is None:
        raise InvalidParcelId("give a parcel identifier or lonlat=(lon, lat)")
    if with_catchment is None:
        # A full report always takes the margin grid (the terrain model reads it); a request for chosen
        # sources keeps the old rule, so a targeted call does not pay for a download nobody reads.
        catchment = sources is None or d8_wins()
    else:
        catchment = with_catchment
    pid = normalize_parcel_id(parcel_id) if parcel_id is not None else ""
    wanted = set(sources or DEFAULT_SOURCES) | {"parcel"}
    previous = config._offline_override
    if offline is not None:
        config.set_offline(offline)
    try:
        if parcel_id is not None:
            parcel_task = _Task("parcel", lambda: fetch_parcel(pid, deadline=total_deadline))
        else:
            parcel_task = _Task(
                "parcel", lambda: fetch_parcel_by_lonlat(lonlat[0], lonlat[1], deadline=total_deadline)
            )
        parcel_res = _vet_parcel(
            parcel_task.collect(min(total_deadline, started + config.TIMEOUTS["parcel"]))
        )
        results: dict[str, SourceResult[Any]] = {"parcel": parcel_res}
        others = [n for n in ALL_SOURCES if n != "parcel"]
        if not parcel_res.usable:
            for name in others:
                results[name] = _empty(name, "skipped", 0, note="parcel unavailable")
        else:
            parcel = parcel_res.data
            lon, lat = parcel.centroid_4326
            now = time.monotonic()
            limits = {n: min(total_deadline, now + config.TIMEOUTS[n]) for n in others}
            if catchment:
                limits["terrain"] = min(total_deadline, now + CATCHMENT_BUDGET_S)
            for n in background:
                if n in limits:
                    limits[n] = now + config.BACKGROUND_S
            calls: dict[str, Callable[[], SourceResult[Any]]] = {
                "weather": lambda: fetch_weather(lat, lon, target, deadline=limits["weather"]),
                "ortho": lambda: fetch_ortho(
                    parcel, m_per_px=ortho_m_per_px, max_px=ortho_max_px, deadline=limits["ortho"]
                ),
                "soil": lambda: fetch_soil(lat, lon, deadline=limits["soil"]),
                "satellite": lambda: fetch_satellite(
                    parcel, target, history_years=history_years, deadline=limits["satellite"]
                ),
                "terrain": lambda: fetch_terrain(
                    parcel, deadline=limits["terrain"], with_catchment=catchment
                ),
                "water": lambda: fetch_water(parcel, deadline=limits["water"]),
                "forecast": lambda: fetch_forecast(lat, lon, deadline=limits["forecast"]),
                "seasonal": lambda: fetch_seasonal(lat, lon, deadline=limits["seasonal"]),
                "crop_hint": lambda: fetch_crop_hint(parcel, deadline=limits["crop_hint"]),
            }
            tasks = {n: _Task(n, calls[n]) for n in others if n in wanted}
            for name in others:
                if name in tasks and name not in background:
                    results[name] = tasks[name].collect(limits[name])
            grace = min(total_deadline, time.monotonic() + config.BACKGROUND_GRACE_S)
            for name in others:
                if name in tasks and name in background:
                    results[name] = tasks[name].collect(grace)
                    if results[name].status == "timeout":
                        results[name].error = "pobieranie trwa w tle; odśwież raport za chwilę"
                elif name not in tasks:
                    results[name] = _empty(name, "skipped", 0, note="not requested")
    finally:
        if offline is not None:
            config.set_offline(previous)
    return FetchResult(
        parcel_id=parcel_res.data.id if parcel_res.usable else pid,
        date=target.isoformat(),
        total_ms=int((time.monotonic() - started) * 1000),
        budget_s=budget_s,
        **results,
    )
