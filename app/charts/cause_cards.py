"""Cause cards: one small card per diagnosed cause, one number and one indicator each. No new calculation:
every figure comes from the diagnosis' evidence or the soil record."""

from __future__ import annotations

import math

from app.charts import svg
from app.fmt import dec, svg_text
from app.models import Cause, Report

W, H = 200, 96
RING_R = 22
TITLES = {
    "malo_opadu": "Opad",
    "duze_parowanie": "Parowanie",
    "gleba_lekka": "Gleba",
    "splyw": "Spadek",
    "faza_wrazliwa": "Faza uprawy",
}
CAPTIONS = {
    "malo_opadu": "Za mało opadu: opad do zwykłego",
    "duze_parowanie": "Duże parowanie: parowanie do zwykłego",
    "gleba_lekka": "Gleba słabo trzyma wodę: udział piasku",
    "splyw": "Woda spływa z pola: średni spadek terenu",
    "faza_wrazliwa": "Uprawa w wrażliwej fazie: okres z progiem",
}
ICONS = {  # 24 px outline icons drawn at (6, 6)
    "malo_opadu": "M18 6l7 11a8 8 0 1 1 -14 0z",
    "duze_parowanie": "M10 26c0 -6 6 -6 6 -12m6 12c0 -6 6 -6 6 -12 M8 12h4 M20 12h4",
    "gleba_lekka": "M6 28l8 -10l6 5l10 -13 M6 30h24",
    "splyw": "M6 10l22 12 M20 22h8v-8",
    "faza_wrazliwa": "M18 30v-14 M18 16c-6 0 -8 -4 -8 -8c6 0 8 4 8 8 M18 20c6 0 8 -4 8 -8c-6 0 -8 4 -8 8",
}


def _ring(share: float, cx: float, cy: float, dry: bool) -> str:
    """Ring: the arc is the share of the usual value, capped at one full turn."""
    frac = max(0.0, min(share, 1.0))
    circ = 2 * math.pi * RING_R
    fg = "ring-dry" if dry else "ring-fg"
    return (
        f'<circle class="ring-bg" cx="{cx}" cy="{cy}" r="{RING_R}"/>'
        f'<circle class="{fg}" cx="{cx}" cy="{cy}" r="{RING_R}" stroke-dasharray="{frac * circ:.1f} {circ:.1f}" '
        f'transform="rotate(-90 {cx} {cy})"/>'
    )


def _card(report: Report, c: Cause) -> str | None:
    e = c.evidence
    indicator = ""
    number: str | None = None
    if c.code == "malo_opadu" and isinstance(e.get("opad_do_zwyklego_proc"), int | float):
        pct = float(e["opad_do_zwyklego_proc"])  # type: ignore[arg-type]
        number, indicator = f"{dec(pct)}%", _ring(pct / 100, 164, 56, dry=True)
    elif c.code == "duze_parowanie" and isinstance(e.get("parowanie_do_zwyklego_proc"), int | float):
        pct = float(e["parowanie_do_zwyklego_proc"])  # type: ignore[arg-type]
        number, indicator = f"{dec(pct)}%", _ring(min(pct, 200) / 200, 164, 56, dry=True)
    elif c.code == "gleba_lekka":
        s = report.soil
        if s.sand_pct is not None:
            number = f"{dec(s.sand_pct)}%"
            silt, clay = s.silt_pct or 0.0, s.clay_pct or 0.0
            total = max(s.sand_pct + silt + clay, 1.0)
            x, parts = 8.0, []
            for value, cls in ((s.sand_pct, "s-warn"), (silt, "s-neu"), (clay, "s-ok")):
                w = (W - 16) * value / total
                parts.append(svg.rect(x, 74, w, 12, cls))
                x += w
            indicator = "".join(parts)
        elif s.category is not None:
            number = f"kat. {s.category}"
    elif c.code == "splyw" and isinstance(e.get("spadek_proc"), int | float):
        slope = float(e["spadek_proc"])  # type: ignore[arg-type]
        number = f"{dec(slope, 1)}%"
        angle = min(math.degrees(math.atan(slope / 100)) * 3, 70)  # exaggerated so a gentle slope is visible
        indicator = f'<path class="arrow" d="M140 50h48m-10 -8l10 8l-10 8" transform="rotate({angle:.0f} 164 50)"/>'
    elif c.code == "faza_wrazliwa" and isinstance(e.get("okres"), int | float):
        n = int(e["okres"])  # type: ignore[arg-type]
        number = f"okres {n}"
        cells = "".join(svg.rect(8 + i * 13.4, 74, 11, 12, "s-ok" if i + 1 == n else "s-neu") for i in range(14))
        indicator = cells
    if number is None:
        return None
    label = f"{CAPTIONS[c.code]}: {number}"
    icon = f'<path class="ic" transform="translate(0 -2) scale(.9)" d="{ICONS[c.code]}"/>'
    body = icon + svg.text(40, 26, TITLES[c.code], "") + svg.text(8, 62, number, "num") + indicator
    chart = svg.svg(H, label, [body])
    return (
        f'<li class="cause-card" data-cause="{c.code}">{chart}'
        f'<span class="cause-cap">{svg_text(CAPTIONS[c.code])}</span></li>'
    )


def cause_cards_html(report: Report) -> str:
    cards = [html for c in report.diagnosis.causes if (html := _card(report, c))]
    return f'<ul class="cause-grid" id="przyczyny-karty">{"".join(cards)}</ul>' if cards else ""
