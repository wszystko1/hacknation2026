"""Section 2 chart: the calibration curve, the share of "+" symbols of SMSR by the margin KBW - threshold.

One point per margin class (squares, as the other charts use rects), a whisker for the 95% interval drawn
over communes, a dashed line at the threshold and a vertical mark at the class of the parcel (`data-marker`).
Numbers come from metrics.json; the chart computes nothing.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.charts import svg
from app.fmt import dec
from app.validation import calibration

HEIGHT = 330
LEFT, RIGHT = 64, 590
TOP, BASE = 56, 230  # 100% and 0%
VARIANT = "fao56"


def _y(share: float) -> float:
    return BASE - share * (BASE - TOP)


def calibration_svg(metrics: Mapping[str, Any], margin_mm: float | None, label: str) -> str:
    """ "" when the curve was not measured; otherwise the SVG. The parcel's class gets the `data-marker` line."""
    points = []
    for i, cls in enumerate(calibration.CLASSES):
        share = metrics.get(f"smsr.calibration.{VARIANT}.{cls.key}.plus_share")
        if share is not None:
            points.append((i, cls, share))
    if not points:
        return ""
    slot = (RIGHT - LEFT) / len(calibration.CLASSES)
    body = []
    for tick in (0.0, 0.5, 1.0):
        body.append(svg.line(LEFT, _y(tick), RIGHT, _y(tick), "ax-zero" if tick == 0 else "grid"))
        body.append(svg.text(LEFT - 8, _y(tick) + 5, f"{round(100 * tick)}%", "", "end"))
    zero_x = LEFT + slot * calibration.CUTS.index(0) + slot
    body.append(svg.line(zero_x, TOP - 8, zero_x, BASE, "s-thr"))
    own = calibration.class_index(margin_mm) if margin_mm is not None else None
    if own is not None:
        cx = LEFT + slot * (own + 0.5)
        mark = svg.line(cx, 26, cx, BASE, "s-date").replace(
            "<line ", f'<line data-marker="{calibration.CLASSES[own].key}" '
        )
        body.append(mark)
        body.append(svg.text(cx, 18, f"działka: {dec(margin_mm, 0)} mm", "lbl-acc", "middle"))
    for i, cls, share in points:
        cx = LEFT + slot * (i + 0.5)
        lo = metrics.get(f"smsr.calibration.{VARIANT}.{cls.key}.ci_low")
        hi = metrics.get(f"smsr.calibration.{VARIANT}.{cls.key}.ci_high")
        if lo is not None and hi is not None:
            body.append(svg.line(cx, _y(hi), cx, _y(lo), "ax-zero"))
        body.append(svg.rect(cx - 6, _y(share) - 6, 12, 12, "s-dry"))
        label_y = _y(hi if hi is not None else share) - 10
        if i == own:  # the parcel's line runs through the class: the share stands beside it, not on it
            body.append(svg.text(cx + 9, label_y - 22, f"{round(100 * share)}%", "lbl", "start"))
        else:
            body.append(svg.text(cx, label_y, f"{round(100 * share)}%", "lbl", "middle"))
    for j, cut in enumerate(calibration.CUTS):
        x = LEFT + slot * (j + 1)
        body.append(svg.text(x, BASE + 22, f"{cut:g}".replace("-", "−"), "", "middle"))
    body.append(svg.text(LEFT, BASE + 48, "← poniżej progu · bilans minus próg, mm · powyżej progu →", ""))
    body.append(svg.line(LEFT, HEIGHT - 22, LEFT + 36, HEIGHT - 22, "s-thr"))
    body.append(svg.text(LEFT + 44, HEIGHT - 16, "próg suszy", ""))
    return svg.svg(
        HEIGHT, label, body, desc=label, title="Odsetek „+” w SMSR wśród symboli o danym marginesie"
    )
