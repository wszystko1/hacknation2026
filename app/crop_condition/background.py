"""Season history of a parcel from Sentinel-2, computed in a background thread after the main report.

The report never waits for it: the first request starts the thread and shows "ocena roślin w toku"; a later
request finds the finished seasons in the cache (outside the files tracked by git). The two demo parcels carry a
frozen copy in demo/data/satellite, so the demo and the tests have the assessment at once and without a network.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Literal

from app.geodata import SceneIndex, cache, config, normalize_parcel_id
from app.geodata.models import Parcel
from app.geodata.satellite import fetch_season

SEASONS_BACK = 6  # earlier seasons read for the comparison (three comparable ones are needed)
JOB_BUDGET_S = 600.0  # the thread gives up after this long
RETRY_AFTER_S = 600.0  # a failed job is not started again sooner than this
NAMESPACE = "satellite_seasons"

Seasons = dict[int, list[SceneIndex]]
Status = Literal["ready", "waiting", "missing"]

_lock = threading.Lock()
_running: dict[str, threading.Thread] = {}
_failed: dict[str, tuple[float, str]] = {}  # key -> (time of failure, reason)


def frozen_dir() -> Path:
    return config.repo_root() / "demo" / "data" / "satellite"


def frozen_path(parcel_id: str) -> Path:
    return frozen_dir() / f"{normalize_parcel_id(parcel_id).replace('/', '_').replace('.', '_')}.json"


def _decode(raw: dict) -> Seasons:
    return {int(y): [SceneIndex(**r) for r in readings] for y, readings in raw.items()}


def encode(seasons: Seasons) -> dict:
    return {str(y): [asdict(r) for r in readings] for y, readings in sorted(seasons.items())}


def load_frozen(parcel_id: str, day: date) -> Seasons | None:
    """The committed copy of the seasons of this parcel when it covers the year of `day`."""
    path = frozen_path(parcel_id)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    seasons = _decode(data["seasons"])
    return seasons if day.year in seasons else None


def _key(parcel_id: str, day: date) -> str:
    # The current season is read up to `day`, so the day is part of the key; finished seasons are shared.
    return f"{normalize_parcel_id(parcel_id)}_{day.isoformat()}"


def load_cached(parcel_id: str, day: date) -> Seasons | None:
    hit = cache.get_json(NAMESPACE, _key(parcel_id, day))
    return None if hit is None else _decode(hit)


def compute(parcel: Parcel, day: date, deadline: float | None = None) -> Seasons:
    """Readings of the season of `day` (up to `day`) and of the SEASONS_BACK seasons before it."""
    seasons: Seasons = {}
    for year in range(day.year - SEASONS_BACK, day.year + 1):
        seasons[year] = fetch_season(parcel, year, day if year == day.year else None, deadline)
    return seasons


def _job(parcel: Parcel, day: date, key: str) -> None:
    try:
        seasons = compute(parcel, day, time.monotonic() + JOB_BUDGET_S)
        if not any(seasons.values()):
            raise RuntimeError("katalog Sentinel-2 nie zwrócił żadnego czystego zdjęcia")
        cache.put_json(NAMESPACE, key, encode(seasons))
    except Exception as exc:  # noqa: BLE001 - the thread must end in a state the report can read
        with _lock:
            _failed[key] = (time.monotonic(), str(exc) or type(exc).__name__)
    finally:
        with _lock:
            _running.pop(key, None)


def seasons_for(parcel: Parcel, day: date) -> tuple[Status, Seasons, str]:
    """(status, seasons, reason): the copy, the cache, or a thread started now.

    "waiting" while the thread runs; "missing" when there is no copy and no network, or the thread failed.
    """
    frozen = load_frozen(parcel.id, day)
    if frozen is not None:
        return "ready", frozen, ""
    cached = load_cached(parcel.id, day)
    if cached is not None:
        return "ready", cached, ""
    if config.is_offline():
        return "missing", {}, "brak kopii zdjęć tej działki i brak połączenia z internetem"
    key = _key(parcel.id, day)
    with _lock:
        if key in _running:
            return "waiting", {}, ""
        failure = _failed.get(key)
        if failure is not None and time.monotonic() - failure[0] < RETRY_AFTER_S:
            return "missing", {}, f"pobranie zdjęć nie powiodło się ({failure[1]})"
        thread = threading.Thread(
            target=_job, args=(parcel, day, key), name="crop-condition-history", daemon=True
        )
        _running[key] = thread
        thread.start()
    return "waiting", {}, ""
