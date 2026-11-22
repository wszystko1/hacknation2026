"""Calibration curve of the method against SMSR: the share of "+" symbols by the margin KBW - threshold.

The margin is in mm, negative when the balance is below the threshold. Eight classes cut at -50, -25, -10, 0,
10, 25 and 50 mm. A value on a negative cut goes to the lower class (further below the threshold), a value on
a cut of zero or more goes to the upper class (further above it):

    m <= -50 | -50 < m <= -25 | -25 < m <= -10 | -10 < m < 0 | 0 <= m < 10 | 10 <= m < 25 | 25 <= m < 50 | m >= 50

So -25 is in "-50 do -25" and 25 is in "25 do 50"; 0 is "not below the threshold", as in the verdict.
Above 50 mm one class: beyond it SMSR says "+" almost never, and the classes would have too few symbols.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

CUTS: tuple[float, ...] = (-50, -25, -10, 0, 10, 25, 50)
UNCERTAIN_MM = 10.0  # |margin| below this: the result is called uncertain


@dataclass(frozen=True)
class MarginClass:
    key: str  # used in the keys of metrics.json
    label: str  # shown to the reader
    phrase: str  # "Gdy bilans działki jest <phrase>"


CLASSES: tuple[MarginClass, ...] = (
    MarginClass("le_m50", "−50 i niżej", "o 50 mm i więcej poniżej progu"),
    MarginClass("m50_m25", "−50 do −25", "od 25 do 50 mm poniżej progu"),
    MarginClass("m25_m10", "−25 do −10", "od 10 do 25 mm poniżej progu"),
    MarginClass("m10_0", "−10 do 0", "do 10 mm poniżej progu"),
    MarginClass("0_10", "0 do 10", "do 10 mm powyżej progu"),
    MarginClass("10_25", "10 do 25", "od 10 do 25 mm powyżej progu"),
    MarginClass("25_50", "25 do 50", "od 25 do 50 mm powyżej progu"),
    MarginClass("ge_50", "50 i więcej", "o 50 mm i więcej powyżej progu"),
)
BY_KEY = {c.key: c for c in CLASSES}


def class_index(margin_mm: float) -> int:
    """Index in CLASSES of a margin; the rule for values on a cut is in the module docstring."""
    for i, cut in enumerate(CUTS):
        if (margin_mm <= cut) if cut < 0 else (margin_mm < cut):
            return i
    return len(CUTS)


def class_of(margin_mm: float) -> MarginClass:
    return CLASSES[class_index(margin_mm)]


def is_uncertain(margin_mm: float) -> bool:
    return abs(margin_mm) < UNCERTAIN_MM


def class_counts(margin: np.ndarray, observed: np.ndarray) -> np.ndarray:
    """(classes, 2) counts of symbols and of "+" symbols; NaN margins are left out."""
    out = np.zeros((len(CLASSES), 2), dtype=np.int64)
    for m, o in zip(margin.tolist(), observed.tolist(), strict=True):
        if math.isnan(m):
            continue
        i = class_index(m)
        out[i, 0] += 1
        out[i, 1] += bool(o)
    return out


def plus_share(counts: np.ndarray) -> list[float | None]:
    return [float(p / n) if n else None for n, p in counts.tolist()]


def per_commune_class_counts(
    margin: np.ndarray, observed: np.ndarray, commune: np.ndarray, communes: Sequence[str]
) -> np.ndarray:
    """(communes, classes, 2) counts for the bootstrap, whose unit of draw is the commune."""
    index = {c: i for i, c in enumerate(communes)}
    out = np.zeros((len(communes), len(CLASSES), 2), dtype=np.int64)
    for m, o, c in zip(margin.tolist(), observed.tolist(), commune.tolist(), strict=True):
        if math.isnan(m):
            continue
        i = class_index(m)
        out[index[c], i, 0] += 1
        out[index[c], i, 1] += bool(o)
    return out


def bootstrap_plus_share(
    counts: np.ndarray, reps: int = 2000, seed: int = 2026
) -> list[tuple[float, float] | None]:
    """95% interval of the "+" share per class, communes (axis 0 of `counts`) drawn with replacement."""
    rng = np.random.default_rng(seed)
    draw = rng.integers(0, len(counts), size=(reps, len(counts)))
    sums = counts[draw].sum(axis=1)  # (reps, classes, 2)
    out: list[tuple[float, float] | None] = []
    for i in range(len(CLASSES)):
        n, p = sums[:, i, 0].astype(float), sums[:, i, 1].astype(float)
        share = p[n > 0] / n[n > 0]
        out.append(tuple(float(x) for x in np.percentile(share, [2.5, 97.5])) if len(share) else None)  # type: ignore[arg-type]
    return out


def confirm_share(counts: np.ndarray, upto_class: int = 1) -> tuple[float | None, int]:
    """Share of "+" over the classes 0..upto_class (default: margin <= -25 mm) and the number of symbols."""
    n = int(counts[: upto_class + 1, 0].sum())
    p = int(counts[: upto_class + 1, 1].sum())
    return (p / n if n else None), n
