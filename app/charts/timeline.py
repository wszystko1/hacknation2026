"""Timeline of the plan: actions by deadline up to the end of the next drought window.

The window ends with the last of the 14 periods of the regulation for which a threshold exists for the crop
group. For past dates the periods that ended after the assessment date appear too, with the state's
assessment of the commune (SMSR) as it was published.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from html import escape
from typing import Literal

from app.drought.kbw import PERIODS, period_dates, season_of
from app.drought.thresholds import threshold_mm
from app.fmt import day
from app.models import Action, CropGroup, SoilCategory

SOILS: tuple[SoilCategory, ...] = ("I", "II", "III", "IV")


@dataclass(frozen=True)
class Entry:
    kind: Literal["action", "past", "end"]
    when: date | None  # None: the action has no deadline
    label: str  # the text in the date column
    text: str
    n: int | None = None  # action number
    in_plan: bool = False


def next_window_year(today: date) -> int:
    """Season year of the next drought window: the running one, or the one that starts on 21.III."""
    year, in_monitoring = season_of(today)
    if in_monitoring:
        return year
    return year + 1 if today.month >= 10 else year


def last_threshold_period(crop: CropGroup, soil: SoilCategory | None) -> int | None:
    """Number of the last period that has a threshold for the crop group (any soil when the soil is unknown)."""
    soils = (soil,) if soil else SOILS
    found = [n for n, _, _ in PERIODS if any(threshold_mm(crop, s, n) is not None for s in soils)]
    return found[-1] if found else None


def window_end(day_: date, crop: CropGroup, soil: SoilCategory | None) -> tuple[date, int] | None:
    """(last day, period number) of the next window, or None when the crop has no thresholds."""
    n = last_threshold_period(crop, soil)
    if n is None:
        return None
    year = next_window_year(day_)
    end = period_dates(year, n)[1]
    if end < day_:  # the season's last period is over: the next window is next year's
        end = period_dates(year + 1, n)[1]
    return end, n


def action_entry(a: Action) -> Entry:
    if a.due is not None:
        return Entry("action", a.due, day(a.due), f"{a.n}. {a.title}", a.n, a.in_plan)
    return Entry("action", None, a.when or "bez terminu", f"{a.n}. {a.title}", a.n, a.in_plan)


def build_entries(actions: list[Action], end: tuple[date, int] | None, past: list[Entry]) -> list[Entry]:
    """Dated entries by date (ties by action number), then the actions without a deadline."""
    dated = [action_entry(a) for a in actions if a.due is not None] + past
    if end is not None:
        dated.append(Entry("end", end[0], day(end[0]), f"koniec okresu {end[1]}: ostatniego z progiem suszy"))
    dated.sort(key=lambda e: (e.when or date.max, e.kind != "action", e.n or 0))
    undated = sorted((action_entry(a) for a in actions if a.due is None), key=lambda e: e.n or 0)
    return dated + undated


def render(entries: list[Entry]) -> str:
    """The timeline as an ordered list; the switches in the sections toggle `is-planned` on the rows."""
    rows = []
    for e in entries:
        label, text = escape(e.label), escape(e.text)
        if e.kind == "action":
            cls = "is-planned" if e.in_plan else ""
            rows.append(f'<li class="{cls}" data-plan-item="{e.n}"><span>{label}</span>{text}<em></em></li>')
        else:
            rows.append(f'<li class="tl-{e.kind}"><span>{label}</span>{text}</li>')
    return f'<ol class="tl" aria-label="Oś czasu planu">{"".join(rows)}</ol>'
