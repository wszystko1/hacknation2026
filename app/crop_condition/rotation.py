"""Rotation group of one season, read from the NDVI curve of the parcel with simple phenology rules.

The group is what the satellite saw on the parcel, not what the farmer enters today: winter crops are green in
March and harvested in July; spring crops start in April-May and peak in June; late crops start in June and
peak in August; grassland stays green all season and is mown; bare soil never turns green.
All thresholds below are the team's proposal, chosen from typical Polish crop calendars, not fitted to data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from statistics import median

from app.geodata import SceneIndex
from app.models import SeasonGroup

# Share of clear pixels a reading needs to count (the nearest-scene search in app.geodata uses the same 0.5).
MIN_CLEAR_SHARE = 0.5  # team proposal
# Readings a season needs before its group is named.
MIN_READINGS = 4  # team proposal
# NDVI at which a field leaves bare soil (bare soil sits at 0.1-0.25).
GREEN_UP_NDVI = 0.3  # team proposal
# Spring crops leave bare soil by the end of May; later than that is a late crop.
LATE_START = (6, 1)  # team proposal
# A harvest or a cut is a fall of at least 0.15 NDVI at a rate of at least 0.02 per day between two readings;
# ripening loses about 0.015 per day, so a long gap between cloudy scenes is not read as a harvest.
DROP_MIN = 0.15  # team proposal
DROP_PER_DAY = 0.02  # team proposal
# After a cut grass regrows to this share of its level before the cut within this many days.
REGROWTH_SHARE = 0.7  # team proposal
REGROWTH_DAYS = 45  # team proposal
# A drop before 1 July without regrowth is a first cut; later it is the harvest of a winter crop.
HARVEST_FROM = (7, 1)  # team proposal
# A green start in March: grassland is greener than winter crops at that time.
GRASS_MARCH_NDVI = 0.55  # team proposal
# Still green in the second half of August: grassland, not a harvested crop.
GREEN_IN_AUGUST = (8, 15, 0.5)  # team proposal: month, day, NDVI
# After the last drop the picture counts as "after harvest" until NDVI is back above this share of the old level.
RECOVERED_SHARE = 0.75  # team proposal


@dataclass(frozen=True)
class Point:
    """One clear reading of the season."""

    day: date
    ndvi: float
    ndmi: float | None
    scene: SceneIndex


def usable_points(readings: list[SceneIndex]) -> list[Point]:
    """Clear readings with an NDVI, one per day (the clearest), oldest first."""
    best: dict[date, SceneIndex] = {}
    for r in readings:
        if r.ndvi is None or r.valid_fraction < MIN_CLEAR_SHARE:
            continue
        d = date.fromisoformat(r.date)
        if d not in best or r.valid_fraction > best[d].valid_fraction:
            best[d] = r
    return [Point(d, s.ndvi, s.ndmi, s) for d, s in sorted(best.items()) if s.ndvi is not None]


def sharp_drops(points: list[Point]) -> list[int]:
    """Indexes i where NDVI fell sharply between points[i - 1] and points[i]."""
    out = []
    for i in range(1, len(points)):
        gap = max((points[i].day - points[i - 1].day).days, 1)
        fall = points[i - 1].ndvi - points[i].ndvi
        if fall >= DROP_MIN and fall / gap >= DROP_PER_DAY:
            out.append(i)
    return out


def regrows(points: list[Point], i: int) -> bool:
    """After the drop at index i NDVI is back to REGROWTH_SHARE of its old level within REGROWTH_DAYS."""
    before = points[i - 1].ndvi
    return any(
        p.ndvi >= REGROWTH_SHARE * before
        for p in points[i + 1 :]
        if (p.day - points[i].day).days <= REGROWTH_DAYS
    )


def after_harvest(points: list[Point]) -> bool:
    """The last reading follows a sharp drop and NDVI has not come back: a harvest or a cut, not stress."""
    drops = sharp_drops(points)
    if not drops:
        return False
    return points[-1].ndvi < RECOVERED_SHARE * points[drops[-1] - 1].ndvi


def starts_green(points: list[Point]) -> bool:
    return median(p.ndvi for p in points[:3]) >= GREEN_UP_NDVI


def green_up(points: list[Point]) -> date | None:
    """Start of vegetation: the day NDVI first crosses GREEN_UP_NDVI (linear between readings).

    A season that is already green at its first reading (winter crops, grassland) starts at that reading.
    """
    if not points:
        return None
    if starts_green(points):
        return points[0].day
    for a, b in zip(points, points[1:], strict=False):
        if a.ndvi < GREEN_UP_NDVI <= b.ndvi:
            share = (GREEN_UP_NDVI - a.ndvi) / (b.ndvi - a.ndvi)
            return date.fromordinal(a.day.toordinal() + round(share * (b.day - a.day).days))
    return None


def classify_points(points: list[Point]) -> SeasonGroup | None:
    """Group of a curve; None when there are too few readings to say."""
    if len(points) < MIN_READINGS:
        return None
    if max(p.ndvi for p in points) < GREEN_UP_NDVI:
        return "gola_gleba"
    if not starts_green(points):
        up = green_up(points)
        if up is None:
            return "gola_gleba"
        return "pozne" if (up.month, up.day) >= LATE_START else "jare"
    # Green in March: winter crop or grassland.
    drops = sharp_drops(points)
    for i in drops:
        if regrows(points, i) or (points[i].day.month, points[i].day.day) < HARVEST_FROM:
            return "tuz"
    if drops:
        return "ozime"
    month, day, level = GREEN_IN_AUGUST
    last = points[-1]
    if (last.day.month, last.day.day) >= (month, day) and last.ndvi >= level:
        return "tuz"
    return "tuz" if median(p.ndvi for p in points[:3]) >= GRASS_MARCH_NDVI else "ozime"


def classify_season(readings: list[SceneIndex]) -> SeasonGroup | None:
    """Rotation group of one season from its readings: ozime, jare, pozne, tuz or gola_gleba.

    Returns None when fewer than MIN_READINGS clear readings exist.
    """
    return classify_points(usable_points(readings))
