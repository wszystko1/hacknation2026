"""Where the data for one parcel and date come from: a frozen copy in demo/data, the disk cache, or live.

A frozen copy of a later date also serves earlier dates of the same parcel: weather is cut at the requested
day. The label is "kopia danych z <date of the download>"; the report adds "pobranie trwało <seconds> s" from
original_download_s: the sum of the per-source times of the original download, the numbers the sources table shows.
"""

from __future__ import annotations

import dataclasses
import os
from datetime import date

from app.geodata import FetchResult, fetch_all, list_samples, load_sample, normalize_parcel_id

# The sources whose time the report lists (rows of the sources table), in the data layer's names.
LISTED_SOURCES = ("parcel", "ortho", "weather", "soil", "terrain", "water", "satellite", "forecast")
LIVE_BUDGET_S = 25.0
HISTORY_YEARS = 5


def original_download_s(result: FetchResult) -> float:
    """Sum of the per-source times of the original download, each rounded to 0.1 s like the report rows."""
    return round(sum(round(getattr(result, n).elapsed_ms / 1000, 1) for n in LISTED_SOURCES), 1)


def _copy_label(result: FetchResult) -> str:
    stamps = [s.retrieved_at for s in result.sources().values() if s.retrieved_at]
    day = max(stamps)[:10] if stamps else result.date
    y, m, d = day.split("-")
    return f"kopia danych z {d}.{m}.{y}"


def _cut_weather(result: FetchResult, day: date) -> FetchResult:
    w = result.weather.data
    if w is None:
        return result
    keep = [i for i, d in enumerate(w.dates) if d <= day.isoformat()]
    cut = dataclasses.replace(
        w,
        dates=[w.dates[i] for i in keep],
        precipitation_mm=[w.precipitation_mm[i] for i in keep],
        et0_mm=[w.et0_mm[i] for i in keep],
    )
    weather = dataclasses.replace(result.weather, data=cut)
    return dataclasses.replace(result, date=day.isoformat(), weather=weather)


def frozen_copy(parcel_id: str, day: date) -> FetchResult | None:
    """The committed copy for this parcel covering `day` (exact date first, then a later copy cut to `day`)."""
    pid = normalize_parcel_id(parcel_id)
    exact = load_sample(pid, day.isoformat())
    if exact is not None:
        return exact
    later = sorted(d for p, d in list_samples() if p == pid and d >= day.isoformat())
    for d in later:
        sample = load_sample(pid, d)
        w = sample.weather.data if sample else None
        if sample and w and w.dates and w.dates[0] <= f"{day.year}-01-01":
            return _cut_weather(sample, day)
    return None


def load(parcel_id: str, day: date, *, budget_s: float = LIVE_BUDGET_S) -> tuple[FetchResult, str | None]:
    """(data, copy label or None). Raises InvalidParcelId for a malformed id; ParcelNotFound shows as status."""
    copy = frozen_copy(parcel_id, day)
    if copy is not None:
        return copy, _copy_label(copy)
    offline = os.environ.get("GEODATA_OFFLINE", "").strip() in {"1", "true", "yes"}
    live = fetch_all(
        parcel_id,
        day,
        budget_s=budget_s,
        offline=offline,
        history_years=HISTORY_YEARS,
        background=("satellite",),
    )
    return live, None
