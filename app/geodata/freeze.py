"""Freeze the demo parcels as committed offline copies, and refuse when the weather has too many gaps.

One command rebuilds every copy: `uv run python scripts/freeze_demo.py`. Weather comes from the IMGW station
index (`python -m app.geodata imgw-sync` builds it once into data/raw/imgw): Open-Meteo's archive refuses
requests over its daily limit, and NASA POWER is a grid of about 50 km that only fills single days.
"""

from __future__ import annotations

import dataclasses
import os
import shutil
import sys
import time
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from . import cache, config, imgw
from .errors import GeodataError
from .models import FetchResult, Weather
from .orchestrator import DEFAULT_SOURCES, fetch_all
from .parcel import fetch_parcel, normalize_parcel_id
from .samples import list_samples, load_sample, save_sample

# Sources that do not depend on the analysis date: when one does not answer at freeze time, the copy takes it
# from the latest committed copy of the same parcel (with its original time and timestamp, and a note).
CARRIED_OVER = ("parcel", "ortho", "soil", "terrain", "water")
SEASON_START = (3, 21)
SEASON_END = (9, 30)
SEASONS = 10
MAX_MISSING_SHARE = 0.05
SATELLITE_HISTORY_YEARS = 5
FREEZE_TIMEOUTS = {"satellite": 90.0, "weather": 40.0}  # a copy is worth waiting for


@dataclass(frozen=True)
class Target:
    parcel_id: str
    day: date


DEMO_TARGETS = (
    Target("040303_2.0002.189/13", date(2023, 7, 20)),
    Target("100403_2.0011.144", date(2026, 11, 21)),
)


class FreezeRefused(Exception):
    """The data are not good enough to be committed as a demo copy."""


def season_gaps(weather: Weather, last_day: date, seasons: int = SEASONS) -> dict[int, float]:
    """Share of days without precipitation or ET0 in each of the `seasons` seasons (21.III-30.IX) up to last_day.

    The last season ends at `last_day` when that day falls inside it. A season without a single day in the
    series counts as fully missing.
    """
    days = {
        d: (p is None or e is None)
        for d, p, e in zip(weather.dates, weather.precipitation_mm, weather.et0_mm, strict=True)
    }
    gaps: dict[int, float] = {}
    for year in range(last_day.year - seasons + 1, last_day.year + 1):
        start, end = date(year, *SEASON_START), min(date(year, *SEASON_END), last_day)
        n = (end - start).days + 1
        missing = sum(
            days.get(date.fromordinal(o).isoformat(), True)
            for o in range(start.toordinal(), end.toordinal() + 1)
        )
        gaps[year] = missing / n if n > 0 else 1.0
    return gaps


def check_seasons(weather: Weather, last_day: date) -> dict[int, float]:
    """The gaps per season, or FreezeRefused when any season misses more than MAX_MISSING_SHARE of its days."""
    gaps = season_gaps(weather, last_day)
    bad = {y: g for y, g in gaps.items() if g > MAX_MISSING_SHARE}
    if bad:
        listed = ", ".join(f"{y}: {g:.1%}" for y, g in sorted(bad.items()))
        raise FreezeRefused(
            f"more than {MAX_MISSING_SHARE:.0%} of weather days missing in the seasons {listed}"
        )
    return gaps


def check_result(result: FetchResult, target: Target) -> dict[int, float]:
    """Raise FreezeRefused unless the result can serve the demo offline; returns the gaps per season."""
    if not result.core_ok:
        raise FreezeRefused(f"parcel or weather missing: {result.parcel.error or result.weather.error}")
    if not result.forecast.usable:
        raise FreezeRefused(f"16-day forecast missing: {result.forecast.error or result.forecast.status}")
    if not result.satellite.usable or result.satellite.data.current is None:
        raise FreezeRefused(
            f"no satellite scene near the date: {result.satellite.error or '; '.join(result.satellite.notes)}"
        )
    return check_seasons(result.weather.data, target.day)


def _previous_copy(parcel_id: str, directory: Path | None) -> FetchResult | None:
    """The latest committed copy of this parcel, any date."""
    days = sorted(d for p, d in list_samples(directory) if p == normalize_parcel_id(parcel_id))
    return load_sample(normalize_parcel_id(parcel_id), days[-1], directory) if days else None


def _seed_parcel(target: Target, previous: FetchResult | None, log) -> None:
    """When ULDK does not answer, put the outline from the previous copy into the cache (original timestamp kept)."""
    try:
        fetch_parcel(target.parcel_id)
        return
    except GeodataError as exc:
        reason = str(exc)[:100]
    if previous is None or not previous.parcel.usable:
        raise FreezeRefused(f"ULDK does not answer ({reason}) and there is no earlier copy of the parcel")
    entry = {
        "data": asdict(previous.parcel.data),
        "url": previous.parcel.source_url,
        "retrieved_at": previous.parcel.retrieved_at,
    }
    cache.put_json("parcel", previous.parcel.data.id, entry)
    cache.put_json("parcel", normalize_parcel_id(target.parcel_id), entry)
    log(f"  ULDK does not answer ({reason}): outline taken from the earlier copy of {previous.date}")


def _carry_over(result: FetchResult, previous: FetchResult | None, log) -> FetchResult:
    """Replace unusable date-independent sources with the ones of the previous copy, keeping their time and timestamp."""
    if previous is None:
        return result
    changes = {}
    for name in CARRIED_OVER:
        have, old = getattr(result, name), getattr(previous, name)
        if have.status == "ok" or old.status != "ok":
            continue
        notes = [n for n in old.notes if not n.startswith("demo sample")]
        notes.append(
            f"service did not answer when the copy was made ({have.error or have.status}); taken from the earlier copy of {previous.date}"
        )
        changes[name] = dataclasses.replace(old, notes=notes)
        log(f"  {name}: {have.status}, taken from the earlier copy of {previous.date}")
    return dataclasses.replace(result, **changes) if changes else result


SATELLITE_ATTEMPTS = 3
SATELLITE_PAUSE_S = 25.0  # the Planetary Computer answers 429 to a burst of requests


def _download(target: Target, log) -> FetchResult:
    """One cold download of every default source; the satellite is repeated (from scratch) when no scene was read."""
    for attempt in range(1, SATELLITE_ATTEMPTS + 1):
        result = fetch_all(
            target.parcel_id, target.day, budget_s=150.0, sources=DEFAULT_SOURCES, ortho_max_px=512,
            history_years=SATELLITE_HISTORY_YEARS, offline=False,
        )  # fmt: skip
        sat = result.satellite
        if (sat.usable and sat.data.current is not None) or attempt == SATELLITE_ATTEMPTS:
            return result
        log(
            f"  satellite without a scene (attempt {attempt}): {'; '.join(sat.notes) or sat.error}; trying again"
        )
        for namespace in ("satellite", "satellite_scene"):
            shutil.rmtree(config.cache_dir() / namespace, ignore_errors=True)
        time.sleep(SATELLITE_PAUSE_S)
    raise AssertionError("unreachable")


def freeze(
    targets: tuple[Target, ...] = DEMO_TARGETS, directory: Path | None = None, log=print
) -> list[Path]:
    """Download every target from scratch (so the times are real) and write the copies; nothing is written on refusal."""
    if imgw.load_index() is None:
        raise FreezeRefused("IMGW station index missing: run `uv run python -m app.geodata imgw-sync` first")
    os.environ["GEODATA_WEATHER"] = "imgw"
    os.environ["GEODATA_IMGW_DIR"] = str(imgw.imgw_dir())  # keep the archive where it is
    work = config.repo_root() / "artifacts" / "tmp" / "freeze_cache"
    shutil.rmtree(work, ignore_errors=True)
    os.environ["GEODATA_CACHE_DIR"] = str(work)
    saved_timeouts = {k: config.TIMEOUTS[k] for k in FREEZE_TIMEOUTS}
    config.TIMEOUTS.update(FREEZE_TIMEOUTS)
    results: list[tuple[Target, FetchResult]] = []
    try:
        previous = {t.parcel_id: _previous_copy(t.parcel_id, directory) for t in targets}
        for target in targets:
            _seed_parcel(target, previous[target.parcel_id], log)
            result = _download(target, log)
            result = _carry_over(result, previous[target.parcel_id], log)
            gaps = check_result(result, target)
            history = len(result.satellite.data.history)
            log(
                f"{target.parcel_id} {target.day}: worst season gap {max(gaps.values()):.1%}, "
                f"satellite history {history} of {SATELLITE_HISTORY_YEARS} seasons, forecast {result.forecast.status}"
            )
            results.append((target, result))
    finally:
        config.TIMEOUTS.update(saved_timeouts)
    return [save_sample(result, directory) for _, result in results]


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        paths = freeze()
    except FreezeRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    for path in paths:
        print(f"saved {path}")
    return 0
