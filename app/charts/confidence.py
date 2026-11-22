"""Reliability of the result for the farmer: a bar with three zones and 100 dots instead of the calibration curve.

The numbers come from the calibration of the method against SMSR in metrics.json (`smsr.calibration.dg.<class>`),
read for the margin class of the parcel. The share of "+" symbols of SMSR is the share of cases in which the state
IUNG confirms a drought; for a parcel above the threshold the agreeing answer is "no drought", so N = 100 - share.
Nothing is computed from the weather here.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.context import load_metrics
from app.fmt import dec
from app.models import Report
from app.validation import calibration

VARIANT = "dg"
SCALE_MM = 50.0  # the bar ends where the last calibration class begins
CAP = 99  # a measured 100% is shown as 99%: nothing is certain
HIGH, MEDIUM = 85, 60  # N from which the label is "wysoka" / "średnia"

# zone (0-10, 10-25, 25-50 mm; widths 20/30/50% in the partial): (name, class keys below the threshold, class keys above it)
ZONES = (
    ("niepewne", ("m10_0",), ("0_10",)),
    ("raczej pewne", ("m25_m10",), ("10_25",)),
    ("pewne", ("m50_m25", "le_m50"), ("25_50", "ge_50")),
)


def _agreement_pct(metrics: Mapping[str, Any], key: str, below: bool) -> int | None:
    share = metrics.get(f"smsr.calibration.{VARIANT}.{key}.plus_share")
    if share is None:
        return None
    return min(CAP, round(100 * (share if below else 1 - share)))


def level(n: int) -> str:
    return "wysoka" if n >= HIGH else "średnia" if n >= MEDIUM else "niska"


def confidence_view(metrics: Mapping[str, Any], margin_mm: float | None) -> dict[str, Any] | None:
    """Data of the partial; None when there is no margin or the class was not measured."""
    if margin_mm is None:
        return None
    below = margin_mm < 0
    n = _agreement_pct(metrics, calibration.class_of(margin_mm).key, below)
    if n is None:
        return None
    zones = []
    for name, keys_below, keys_above in ZONES:
        keys = keys_below if below else keys_above
        values = [v for k in keys if (v := _agreement_pct(metrics, k, below)) is not None]
        if not values:
            text = "brak"
        elif min(values) == max(values):
            text = f"{min(values)}%"
        else:
            text = f"{min(values)}–{max(values)}%"
        zones.append(
            {
                "name": name,
                "text": text,
            }
        )
    distance = abs(margin_mm)
    zone_index = 0 if distance < 10 else 1 if distance < 25 else 2
    zones[zone_index]["own"] = True
    pos = min(100.0, 100 * distance / SCALE_MM)
    verdict_word = ("niepewny", "raczej pewny", "pewny")[zone_index]
    if below:
        sentence = f"Przy takim wyniku państwowa ocena IUNG potwierdza suszę w {n} na 100 przypadków."
    else:
        sentence = (
            f"Przy takim wyniku państwowa ocena IUNG również nie wskazuje suszy w {n} na 100 przypadków."
        )
    return {
        "n": n,
        "level": level(n),
        "label": f"Wiarygodność wyniku: {level(n)}",
        "sentence": f"{sentence} To wynik {verdict_word}.",
        "zone_name": zones[zone_index]["name"],
        "zones": zones,
        "pos": round(pos, 1),
        "side": "right" if pos > 60 else "left",
        "marker": f"{dec(distance)} mm {'poniżej' if below else 'powyżej'} progu",
        "dots": [i < n for i in range(100)],
    }


def confidence_for(report: Report) -> dict[str, Any] | None:
    """The same for a report: the margin of the verdict and the metrics.json of the application."""
    return confidence_view(load_metrics(), report.verdict.margin_mm)
