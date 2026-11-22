"""Crop-phase calendar: March-September as one bar, with the periods in which drought lowers the yield.

The periods come from the regulation's threshold table for the crop and the parcel's soil category.
Periods whose cell is "x" or "-" (no threshold) stay grey. Also drawn: the assessment date and the balance window.
"""

from __future__ import annotations

from datetime import date

from app.charts import svg
from app.drought.kbw import PERIODS
from app.drought.thresholds import threshold_cell
from app.fmt import day_month
from app.models import CropGroup, Report

HEIGHT = 168
LEFT, RIGHT = 20, 580
BAR_TOP, BAR_H = 36, 28
DAYS = 214  # 1 March - 30 September
MONTHS = ("Mar", "Kwi", "Maj", "Cze", "Lip", "Sie", "Wrz")
BASE = date(2001, 3, 1)


def _offset(month: int, day: int) -> int:
    return max(0, min(DAYS, (date(2001, month, day) - BASE).days))


def _x(offset: float) -> float:
    return LEFT + offset * (RIGHT - LEFT) / DAYS


def _has_threshold(cell: str) -> bool:
    return cell not in {"", "x", "-"}


def covered_days(crop: CropGroup, soil: str) -> tuple[set[int], set[int]]:
    """(days inside a period with a threshold, days inside a period without one), as offsets from 1 March."""
    with_thr: set[int] = set()
    without: set[int] = set()
    for n, (sm, sd), (em, ed) in PERIODS:
        days = range(_offset(sm, sd), _offset(em, ed) + 1)
        (with_thr if _has_threshold(threshold_cell(crop, soil, n)) else without).update(days)  # type: ignore[arg-type]
    return with_thr, without - with_thr


def _runs(days: set[int]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for d in sorted(days):
        if out and d == out[-1][1] + 1:
            out[-1] = (out[-1][0], d)
        else:
            out.append((d, d))
    return out


def calendar_svg(report: Report) -> str:
    """"" when the crop has no table (Inna uprawa) or the soil category is unknown."""
    crop, soil = report.request.crop, report.soil.category
    if crop == CropGroup.INNA or soil is None:
        return ""
    with_thr, without = covered_days(crop, soil)
    if not with_thr:
        return ""
    body = [svg.rect(LEFT, BAR_TOP, RIGHT - LEFT, BAR_H, "s-track")]
    for a, b in _runs(without):
        body.append(svg.rect(_x(a), BAR_TOP, _x(b + 1) - _x(a), BAR_H, "s-neu"))
    for a, b in _runs(with_thr):
        body.append(svg.rect(_x(a), BAR_TOP, _x(b + 1) - _x(a), BAR_H, "s-ok"))
    for i, name in enumerate(MONTHS):
        start = _offset(3 + i, 1)
        end = _offset(3 + i + 1, 1) if i < 6 else DAYS
        body.append(svg.line(_x(start), BAR_TOP - 6, _x(start), BAR_TOP, "ax-line"))
        body.append(svg.text(_x((start + end) / 2), BAR_TOP - 12, name, "", "middle"))
    p = report.verdict.period
    if p is not None:
        a, b = _offset(p.start.month, p.start.day), _offset(p.end.month, p.end.day)
        body.append(svg.rect(_x(a), BAR_TOP + BAR_H + 6, _x(b + 1) - _x(a), 8, "s-window"))
        body.append(
            svg.text(_x(a), BAR_TOP + BAR_H + 36, f"okno bilansu {day_month(p.start)}–{day_month(p.end)}", "lbl-dry")
        )
    day = report.request.day
    if 3 <= day.month <= 9:
        mx = _x(_offset(day.month, day.day) + 0.5)
        anchor = "end" if mx > 440 else ("start" if mx < 140 else "middle")
        body.append(svg.line(mx, BAR_TOP - 4, mx, BAR_TOP + BAR_H + 18, "s-date"))
        body.append(svg.text(mx, BAR_TOP + BAR_H + 62, f"data oceny {day_month(day)}", "lbl-acc", anchor))
    ly = HEIGHT - 18
    body.append(svg.rect(LEFT, ly - 12, 16, 12, "s-ok"))
    body.append(svg.text(LEFT + 24, ly, "susza obniża plon", ""))
    body.append(svg.rect(LEFT + 250, ly - 12, 16, 12, "s-neu"))
    body.append(svg.text(LEFT + 274, ly, "bez progu w tabeli", ""))
    label = (
        f"Kalendarz uprawy: okresy z progiem suszy od marca do września; data oceny {day_month(day)}"
        + (f", okno bilansu {day_month(p.start)}–{day_month(p.end)}" if p else "")
    )
    return svg.svg(HEIGHT, label, body, desc=label, title="Kiedy susza obniża plon tej uprawy")
