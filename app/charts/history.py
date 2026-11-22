"""Section 1 chart: one bar per season (its worst finished period), a dash for the threshold, the SMSR mark."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.advice.diagnosis import SeasonWorst
from app.charts import svg
from app.fmt import dec

HEIGHT = 378
LEFT, RIGHT = 74, 590
TOP, BASE = 44, 244  # top of the tallest bar, the zero line
NEAR_MM = 15.0  # a season this close above the threshold is drawn in the warning colour
SMSR_WORDS = {"+": "susza", "-": "brak"}


def _bar_class(s: SeasonWorst) -> str:
    if s.below is None:
        return "s-neu"
    if s.below:
        return "s-dry"
    return "s-warn" if (s.period.margin_mm or 0.0) < NEAR_MM else "s-neu"


def history_svg(seasons: Sequence[SeasonWorst], smsr: Mapping[int, str], label: str) -> str:
    """Bars show the shortfall (minus the balance) in mm; every bar carries its value, so colour is not the only cue."""
    if not seasons:
        return ""
    peak = max(
        max(-s.period.kbw_mm, s.period.threshold_mm and -s.period.threshold_mm or 0.0, 1.0) for s in seasons
    )
    scale = (BASE - TOP) / peak
    slot = (RIGHT - LEFT) / len(seasons)
    bar_w = min(slot * 0.62, 44.0)
    body = [
        svg.line(LEFT, BASE, RIGHT, BASE, "ax-zero"),
    ]
    for i, s in enumerate(seasons):
        cx = LEFT + slot * (i + 0.5)
        shortfall = -s.period.kbw_mm
        h = max(shortfall, 0.0) * scale
        body.append(svg.rect(cx - bar_w / 2, BASE - h, bar_w, h, _bar_class(s)))
        top = BASE - h
        thr = s.period.threshold_mm
        if thr is not None:
            ty = BASE - max(-thr, 0.0) * scale
            body.append(svg.line(cx - slot * 0.45, ty, cx + slot * 0.45, ty, "s-thr"))
            top = min(top, ty)
        body.append(svg.text(cx, top - 8, dec(s.period.kbw_mm), "lbl-dry" if s.below else "lbl", "middle"))
        body.append(svg.text(cx, BASE + 22, str(s.year), "", "middle"))
        mark = SMSR_WORDS.get(smsr.get(s.year, ""))
        if mark:
            body.append(svg.text(cx, BASE + 46, mark, "lbl-dry" if smsr[s.year] == "+" else "", "middle"))
    if smsr:
        body.append(svg.text(0, BASE + 46, "SMSR", "lbl-acc"))
    body.append(svg.text(0, BASE + 22, "sezon", ""))
    for x, y, cls, words in (
        (LEFT, HEIGHT - 62, "s-dry", "poniżej progu"),
        (LEFT + 170, HEIGHT - 62, "s-warn", f"do {dec(NEAR_MM)} mm nad progiem"),
        (LEFT, HEIGHT - 36, "s-neu", "dalej od progu"),
    ):
        body.append(svg.rect(x, y - 13, 14, 14, cls))
        body.append(svg.text(x + 22, y, words, ""))
    body.append(svg.line(LEFT, HEIGHT - 12, LEFT + 36, HEIGHT - 12, "s-thr"))
    body.append(svg.text(LEFT + 44, HEIGHT - 6, "próg suszy z rozporządzenia", ""))
    return svg.svg(HEIGHT, label, body, desc=label, title="Niedobór wody w najgorszym okresie sezonu, mm")
