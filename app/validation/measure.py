"""Measurement of the method against SMSR IUNG on many communes: cases, tables, bootstrap, reference lines.

A case is one cell of an SMSR commune page (commune, year, crop, soil category, period) with a "+" or "-" symbol
and a threshold in the regulation. For the cell we compute the KBW of the period with `app.drought.kbw.period_balance`
and the threshold with `app.drought.thresholds.threshold_mm`, the code the report uses; the method says "below" when
KBW - threshold < 0. A period with more than 10% of days without data is left out, as in the report.

Everything here works on numpy arrays of cases; `scripts/eval_smsr.py` reads the files and writes metrics.json.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

import numpy as np

from app.drought.kbw import MAX_MISSING_SHARE, PERIODS, period_balance
from app.models import CROP_LABELS, ConfusionTable, CropGroup
from app.smsr.parser import CommuneTable
from app.validation.agreement import BUCKETS, bucket_of, confusion, scores

VARIANTS = ("fao56", "dg", "power")
CROPS = [c for c in CropGroup if c != CropGroup.INNA]
SOILS = ("I", "II", "III", "IV")


@dataclass
class Cases:
    """Columns of equal length; `margin_*` is KBW - threshold in mm, NaN where the period has too little data."""

    commune: list[str] = field(default_factory=list)
    year: list[int] = field(default_factory=list)
    key: list[tuple] = field(default_factory=list)  # (crop, soil, period), the cell inside a commune
    observed: list[bool] = field(default_factory=list)  # SMSR says "+"
    margin: dict[str, list[float]] = field(default_factory=lambda: {v: [] for v in VARIANTS})

    def __len__(self) -> int:
        return len(self.commune)


def period_kbw(
    dates: Sequence[str], precip: Sequence[float | None], et0: Sequence[float | None], year: int
) -> dict[int, float]:
    """KBW of every period of `year` that has enough days; the same summation as the report's."""
    first, last = f"{year}-03-01", f"{year}-10-31"
    keep = [i for i, d in enumerate(dates) if first <= d <= last]
    if not keep:
        return {}
    d, p, e = ([seq[i] for i in keep] for seq in (dates, precip, et0))
    out: dict[int, float] = {}
    for n, _, _ in PERIODS:
        pb = period_balance(d, p, e, year, n, date(year, 12, 31), CropGroup.INNA, None)
        if pb is None:
            continue
        window = (pb.end - pb.start).days + 1
        if window - pb.days <= MAX_MISSING_SHARE * window:
            out[n] = pb.kbw_mm
    return out


def add_commune_year(
    cases: Cases, table: CommuneTable, kbw: dict[str, dict[int, float]], thresholds: dict[tuple, float | None]
) -> None:
    """Append the cells of one commune page. `kbw[variant][period]` from `period_kbw`; `thresholds[(crop, soil, n)]`."""
    for crop in CROPS:
        label = CROP_LABELS[crop]
        for soil in SOILS:
            for n, _, _ in PERIODS:
                symbol = table.symbol(label, soil, n)
                thr = thresholds.get((crop, soil, n))
                if symbol not in {"+", "-"} or thr is None:
                    continue
                margins = {v: (kbw[v][n] - thr if n in kbw[v] else float("nan")) for v in VARIANTS}
                if all(np.isnan(m) for m in margins.values()):
                    continue
                cases.commune.append(table.teryt)
                cases.year.append(table.year)
                cases.key.append((crop.value, soil, n))
                cases.observed.append(symbol == "+")
                for v in VARIANTS:
                    cases.margin[v].append(margins[v])


def climatology(cases: Cases) -> np.ndarray:
    """Drought when, in the other years, the same commune and cell had "+" in at least half of them."""
    cells: dict[tuple, dict[int, bool]] = {}
    for c, y, k, o in zip(cases.commune, cases.year, cases.key, cases.observed, strict=True):
        cells.setdefault((c, k), {})[y] = o
    out = np.zeros(len(cases), dtype=bool)
    for i, (c, y, k) in enumerate(zip(cases.commune, cases.year, cases.key, strict=True)):
        others = [v for yy, v in cells[(c, k)].items() if yy != y]
        out[i] = bool(others) and sum(others) >= len(others) / 2
    return out


@dataclass
class View:
    """Arrays of a subset of cases: who says what."""

    commune: np.ndarray
    year: np.ndarray
    observed: np.ndarray
    margin: dict[str, np.ndarray]
    clim: np.ndarray

    def where(self, mask: np.ndarray) -> View:
        return View(
            self.commune[mask], self.year[mask], self.observed[mask],
            {v: m[mask] for v, m in self.margin.items()}, self.clim[mask],
        )  # fmt: skip


def view(cases: Cases) -> View:
    return View(
        np.array(cases.commune),
        np.array(cases.year),
        np.array(cases.observed, dtype=bool),
        {v: np.array(m, dtype=float) for v, m in cases.margin.items()},
        climatology(cases),
    )


def table_of(predicted: np.ndarray, observed: np.ndarray) -> ConfusionTable:
    return confusion(zip(predicted.tolist(), observed.tolist(), strict=True))


def evaluate(v: View, variant: str, shift_mm: float = 0.0) -> tuple[ConfusionTable, dict[str, float | None]]:
    """Table and scores of one variant on the cases it has data for. Below means margin < shift_mm."""
    m = v.margin[variant]
    ok = ~np.isnan(m)
    t = table_of(m[ok] < shift_mm, v.observed[ok])
    return t, scores(t)


def per_commune_counts(
    v: View, predicted: np.ndarray, usable: np.ndarray, communes: Sequence[str]
) -> np.ndarray:
    """(communes, 4) counts of hits, false alarms, misses, correct negatives, for the bootstrap."""
    out = np.zeros((len(communes), 4), dtype=np.int64)
    index = {c: i for i, c in enumerate(communes)}
    rows = np.array([index[c] for c in v.commune[usable]], dtype=int)
    p, o = predicted[usable], v.observed[usable]
    for col, mask in enumerate((p & o, p & ~o, ~p & o, ~p & ~o)):
        np.add.at(out[:, col], rows[mask], 1)
    return out


def _stat(counts: np.ndarray, name: str) -> np.ndarray:
    a, b, c, d = (counts[..., i].astype(float) for i in range(4))
    with np.errstate(divide="ignore", invalid="ignore"):
        if name == "csi":
            return a / (a + b + c)
        if name == "balanced_accuracy":
            return (a / (a + c) + d / (b + d)) / 2
        if name == "ratio_below_to_plus":
            return (a + b) / (a + c)
    raise KeyError(name)


def bootstrap_by_commune(
    counts: np.ndarray, names: Sequence[str], reps: int = 2000, seed: int = 2026
) -> dict[str, tuple[float, float]]:
    """95% interval of each statistic when the communes (rows of `counts`) are drawn with replacement.

    Cases of one commune share weather and soil, so the commune, not the single symbol, is the unit of draw.
    """
    rng = np.random.default_rng(seed)
    draw = rng.integers(0, len(counts), size=(reps, len(counts)))
    sums = counts[draw].sum(axis=1)  # (reps, 4)
    out: dict[str, tuple[float, float]] = {}
    for name in names:
        values = _stat(sums, name)
        values = values[np.isfinite(values)]
        lo, hi = np.percentile(values, [2.5, 97.5]) if len(values) else (float("nan"), float("nan"))
        out[name] = (float(lo), float(hi))
    return out


def agreement_by_distance(v: View, variant: str) -> dict[str, float]:
    """Share of cases where method and SMSR agree, by distance of the KBW from the threshold."""
    m = v.margin[variant]
    ok = ~np.isnan(m)
    names = np.array([bucket_of(x) for x in m[ok]]) if ok.any() else np.array([])
    agree = ((m[ok] < 0) == v.observed[ok]) if ok.any() else np.array([], dtype=bool)
    return {name: float(agree[names == name].mean()) for name, _, _ in BUCKETS if (names == name).any()}


def choose_shift(v: View, variant: str, grid: Sequence[float]) -> float:
    """The shift of the threshold (mm) with the best balanced accuracy on `v`; the smallest |shift| wins a tie."""
    best, best_score = 0.0, -1.0
    for shift in sorted(grid, key=abs):
        score = evaluate(v, variant, shift)[1]["balanced_accuracy"]
        if score is not None and score > best_score + 1e-12:
            best, best_score = float(shift), score
    return best
