"""Charts of the soil and irrigation sections: the 18 decades of IV-IX, once as seasons under the threshold, once as shortfall."""

from __future__ import annotations

from collections.abc import Sequence

from app.advice.rules import DecadeCount, DecadeDeficit
from app.charts import svg
from app.fmt import dec

HEIGHT = 330
LEFT, RIGHT = 8, 592
TOP, BASE = 40, 230
SLOTS = 18
MONTHS = ("IV", "V", "VI", "VII", "VIII", "IX")


def _axis(body: list[str], slot: float, base: float) -> None:
    """Decade numbers 1-3 under the axis, the month once under the middle decade."""
    for i in range(SLOTS):
        cx = LEFT + slot * (i + 0.5)
        body.append(svg.text(cx, base + 22, str(i % 3 + 1), "", "middle"))
        if i % 3 == 1:
            body.append(svg.text(cx, base + 46, MONTHS[i // 3], "lbl", "middle"))


def _legend(body: list[str], y: int, items: Sequence[tuple[str, str]]) -> None:
    x = LEFT
    for cls, words in items:
        body.append(svg.rect(x, y - 13, 14, 14, cls))
        body.append(svg.text(x + 22, y, words, ""))
        x += 30 + 9 * len(words)


def counts_svg(counts: Sequence[DecadeCount], label: str) -> str:
    """One bar per decade: in how many seasons the 60-day window ending on it was under the threshold."""
    judged = max((c.judged for c in counts), default=0)
    if not judged:
        return ""
    slot = (RIGHT - LEFT) / SLOTS
    bar_w = slot * 0.7
    scale = (BASE - TOP) / judged
    body = [
        svg.line(LEFT, BASE, RIGHT, BASE, "ax-zero"),
    ]
    for i, c in enumerate(counts):
        cx = LEFT + slot * (i + 0.5)
        if not c.judged:
            body.append(svg.text(cx, BASE - 8, "–", "", "middle"))
            continue
        h = c.below * scale
        cls = "s-dry" if c.below * 2 >= c.judged else "s-warn" if c.below else "s-neu"
        body.append(svg.rect(cx - bar_w / 2, BASE - h, bar_w, h, cls))
        body.append(
            svg.text(cx, BASE - h - 8, str(c.below), "lbl-dry" if cls == "s-dry" else "lbl", "middle")
        )
    _axis(body, slot, BASE)
    _legend(
        body,
        HEIGHT - 22,
        (("s-dry", "co najmniej połowa sezonów"), ("s-warn", "mniej niż połowa"), ("s-neu", "ani razu")),
    )
    body.append(svg.text(LEFT, HEIGHT - 2, "„–”: w tej dekadzie nie kończy się okres z progiem", ""))
    return svg.svg(
        HEIGHT, label, body, desc=label, title="Sezony pod progiem w oknie 60 dni kończącym się w dekadzie"
    )


def deficit_svg(deficits: Sequence[DecadeDeficit], label: str) -> str:
    """Shortfall (evaporation − rain) per decade; decades in a phase with a threshold stand on a tinted band."""
    values = [d.deficit_mm for d in deficits if d.deficit_mm is not None]
    if not values:
        return ""
    high = max(max(values), 1.0)
    low = min(min(values), 0.0)
    slot = (RIGHT - LEFT) / SLOTS
    bar_w = slot * 0.7
    scale = (BASE - 20 - TOP) / (high - low)
    zero = TOP + high * scale
    body = []
    for i, d in enumerate(deficits):
        if d.sensitive:
            body.append(svg.rect(LEFT + slot * i, TOP - 8, slot, BASE - TOP + 8, "s-window"))
    body.append(svg.line(LEFT, zero, RIGHT, zero, "ax-zero"))
    for i, d in enumerate(deficits):
        if d.deficit_mm is None:
            continue
        cx = LEFT + slot * (i + 0.5)
        v = d.deficit_mm
        h = abs(v) * scale
        if v >= 0:
            cls = "s-dry" if d.sensitive else "s-neu"
            body.append(svg.rect(cx - bar_w / 2, zero - h, bar_w, h, cls))
            body.append(svg.text(cx, zero - h - 6, dec(v), "lbl-dry" if d.sensitive else "lbl", "middle"))
        else:
            body.append(svg.rect(cx - bar_w / 2, zero, bar_w, h, "s-rain"))
            body.append(svg.text(cx, zero + h + 16, dec(v), "lbl", "middle"))
    _axis(body, slot, BASE)
    _legend(
        body,
        HEIGHT - 6,
        (
            ("s-window", "faza z progiem w rozporządzeniu"),
            ("s-dry", "niedobór w tej fazie"),
            ("s-rain", "nadwyżka opadu"),
        ),
    )
    return svg.svg(HEIGHT, label, body, desc=label, title="Niedobór wody w dekadzie (parowanie − opad), mm")
