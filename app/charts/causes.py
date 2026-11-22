"""Section 3 chart: waterfall from the usual balance through less rain and more evaporation to this period's balance."""

from __future__ import annotations

from app.advice.diagnosis import BalanceSplit
from app.charts import svg
from app.fmt import dec

HEIGHT = 362
LEFT, RIGHT = 20, 590
TOP, BOTTOM = 52, 236
LABELS = (("zwykły", "bilans"), ("mniej", "opadu"), ("więcej", "parowania"), ("bilans", "w tym okresie"))


def waterfall_svg(split: BalanceSplit, threshold_mm: float | None, label: str) -> str:
    """Zero line at the top for a deficit; bars hang from it. Each bar carries its value in mm."""
    u, r, e, res = split.usual_mm, split.rain_step_mm, split.evaporation_step_mm, split.result_mm
    spans = [(0.0, u), (u, u + r), (u + r, u + r + e), (0.0, res)]
    classes = [
        "s-neu",
        "s-rain",
        "s-et",
        "s-dry" if threshold_mm is not None and res < threshold_mm else "s-neu",
    ]
    values = [u, r, e, res]
    points = [0.0, *(v for span in spans for v in span)] + (
        [threshold_mm] if threshold_mm is not None else []
    )
    hi, lo = max(points), min(points)
    scale = (BOTTOM - TOP) / max(hi - lo, 1.0)

    def y(v: float) -> float:
        return TOP + (hi - v) * scale

    slot = (RIGHT - LEFT) / 4
    bar_w = slot * 0.56
    body = []
    body.append(svg.line(LEFT, y(0), RIGHT, y(0), "ax-zero"))
    for i, ((a, b), cls, val) in enumerate(zip(spans, classes, values, strict=True)):
        cx = LEFT + slot * (i + 0.5)
        body.append(svg.rect(cx - bar_w / 2, y(max(a, b)), bar_w, abs(y(a) - y(b)), cls))
        if i < 3:  # connector to the next bar
            body.append(svg.line(cx + bar_w / 2, y(b), cx + slot - bar_w / 2, y(b), "ax-line"))
        warn = i == 3 and cls == "s-dry"
        if i in (0, 3):  # bars hanging from the zero line: the value above the line
            body.append(svg.text(cx, y(0) - 8, dec(val), "lbl-dry" if warn else "lbl", "middle"))
        else:  # floating steps: above or under the bar, whichever side keeps clear of the threshold line
            above, below = y(max(a, b)) - 8, y(min(a, b)) + 22
            clear = threshold_mm is None or abs(above - 6 - y(threshold_mm)) > 22
            body.append(svg.text(cx, above if clear else below, dec(val), "lbl", "middle"))
        body.append(svg.text(cx, BOTTOM + 52, LABELS[i][0], "", "middle"))
        body.append(svg.text(cx, BOTTOM + 78, LABELS[i][1], "", "middle"))
    if threshold_mm is not None:
        body.append(svg.line(LEFT, y(threshold_mm), RIGHT, y(threshold_mm), "s-thr"))
        body.append(svg.line(LEFT, HEIGHT - 12, LEFT + 36, HEIGHT - 12, "s-thr"))
        body.append(svg.text(LEFT + 44, HEIGHT - 6, f"próg suszy {dec(threshold_mm)} mm", ""))
    return svg.svg(HEIGHT, label, body, desc=label, title="Bilans okresu, mm (0 u góry; w dół = niedobór)")
