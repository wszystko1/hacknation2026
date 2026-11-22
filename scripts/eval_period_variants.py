"""Which period and which evaporation formula agree best with SMSR: `make eval ONLY=period_variants`.

The report shows the period of the smallest margin (KBW - threshold) among all finished periods of the season
("worst period"). SMSR publishes one table per period; on the day a period ends, its symbol is the report of that day.
For every analysis day = end of period n (the last full dekad of that day) we compare, against the SMSR symbol
of period n ("+" = drought), four predictions on the same cases:

  fao56_worst    FAO-56 ET0, drought when the smallest margin of periods 1..n is below 0 (the app today)
  fao56_current  FAO-56 ET0, drought when the margin of period n is below 0 (what SMSR reports that day)
  dg_worst       Doroszewski-Gorski ET0, worst of periods 1..n
  dg_current     Doroszewski-Gorski ET0, period n

and two reference rows that give the worst period its own like-for-like truth: `fao56_worst_vs_any` and
`dg_worst_vs_any` compare the worst of periods 1..n with "+" in any of the periods 1..n.

Two cases are in the table of a variant only when period n is usable for both formulas (at most 10% of days
without data), so the variants are compared on identical cases. Communes: the "test" communes of
demo/data/eval/gminy.csv, the ones of the `smsr.*` numbers. Intervals: bootstrap by commune (2000 draws),
the difference "current minus worst" is paired (same draws). Writes `smsr_variants.*`; the verdict of the app
is not changed by this evaluation.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import eval_smsr  # noqa: E402

from app.drought.kbw import PERIODS  # noqa: E402
from app.validation import measure  # noqa: E402
from app.validation.agreement import scores  # noqa: E402

N_PERIODS = len(PERIODS)
# name -> (formula, worst of periods 1..n, truth = "+" in any period 1..n instead of in period n)
VARIANTS = {
    "fao56_worst": ("fao56", True, False),
    "fao56_current": ("fao56", False, False),
    "dg_worst": ("dg", True, False),
    "dg_current": ("dg", False, False),
    "fao56_worst_vs_any": ("fao56", True, True),
    "dg_worst_vs_any": ("dg", True, True),
}
NAMES = ("csi", "pod", "far", "balanced_accuracy")


def dense(cases: measure.Cases, communes: set[str]) -> dict[str, np.ndarray]:
    """One row per (commune, year, crop, soil), one column per period; NaN where the cell has no margin.

    `observed` is 1 for "+", 0 for "-", -1 where SMSR has no symbol for the cell.
    """
    index: dict[tuple, int] = {}
    for c, y, (crop, soil, _n) in zip(cases.commune, cases.year, cases.key, strict=True):
        if c in communes:
            index.setdefault((c, y, crop, soil), len(index))
    out = {
        "observed": np.full((len(index), N_PERIODS), -1, dtype=np.int8),
        "commune": np.array([k[0] for k in index], dtype=object),
        **{v: np.full((len(index), N_PERIODS), np.nan) for v in ("fao56", "dg")},
    }
    for i, (c, y, (crop, soil, n)) in enumerate(zip(cases.commune, cases.year, cases.key, strict=True)):
        if c not in communes:
            continue
        row = index[(c, y, crop, soil)]
        out["observed"][row, n - 1] = int(cases.observed[i])
        for v in ("fao56", "dg"):
            out[v][row, n - 1] = cases.margin[v][i]
    return out


def predictions(margin: np.ndarray, worst: bool) -> np.ndarray:
    """Drought flag per (row, period n): the margin of period n, or the smallest margin of periods 1..n."""
    used = np.fmin.accumulate(margin, axis=1) if worst else margin  # fmin skips NaN
    return used < 0


def variant_counts(
    data: dict[str, np.ndarray],
) -> tuple[dict[str, np.ndarray], np.ndarray, np.ndarray, np.ndarray]:
    """(per-commune 2x2 counts per variant, communes, usable mask, observed), shapes (communes, 4)."""
    usable = ~np.isnan(data["fao56"]) & ~np.isnan(data["dg"]) & (data["observed"] >= 0)
    observed_n = data["observed"] == 1
    observed_any = np.maximum.accumulate(observed_n, axis=1)
    communes = np.array(sorted(set(data["commune"].tolist())))
    rows = np.searchsorted(communes, data["commune"])
    counts = {}
    for name, (formula, worst, any_period) in VARIANTS.items():
        predicted = predictions(data[formula], worst)
        observed = observed_any if any_period else observed_n
        table = np.zeros((len(communes), 4), dtype=np.int64)
        for col, mask in enumerate(
            (predicted & observed, predicted & ~observed, ~predicted & observed, ~predicted & ~observed)
        ):
            hit = mask & usable
            np.add.at(table[:, col], np.broadcast_to(rows[:, None], hit.shape)[hit], 1)
        counts[name] = table
    return counts, communes, usable, observed_n


def _stat(counts: np.ndarray, name: str) -> np.ndarray:
    a, b, c, d = (counts[..., i].astype(float) for i in range(4))
    with np.errstate(divide="ignore", invalid="ignore"):
        return {
            "csi": a / (a + b + c),
            "pod": a / (a + c),
            "far": b / (a + b),
            "balanced_accuracy": (a / (a + c) + d / (b + d)) / 2,
        }[name]


def summarise(counts: dict[str, np.ndarray], reps: int = 2000, seed: int = 2026) -> dict[str, float | int]:
    """Point values, bootstrap intervals by commune and paired differences "current minus worst"."""
    n_communes = len(next(iter(counts.values())))
    draw = np.random.default_rng(seed).integers(0, n_communes, size=(reps, n_communes))
    sums = {name: c[draw].sum(axis=1) for name, c in counts.items()}
    out: dict[str, float | int] = {}
    for name, table in counts.items():
        total = table.sum(axis=0)
        t = scores_of(total)
        out[f"smsr_variants.{name}.n_cases"] = int(total.sum())
        for stat in NAMES:
            if t[stat] is not None:
                out[f"smsr_variants.{name}.{stat}"] = round(t[stat], 4)
        for stat in ("csi", "balanced_accuracy"):
            values = _stat(sums[name], stat)
            lo, hi = np.percentile(values[np.isfinite(values)], [2.5, 97.5])
            out[f"smsr_variants.{name}.{stat}_ci_low"] = round(float(lo), 4)
            out[f"smsr_variants.{name}.{stat}_ci_high"] = round(float(hi), 4)
    for formula in ("fao56", "dg"):
        for stat in ("csi", "balanced_accuracy"):
            point = (
                scores_of(counts[f"{formula}_current"].sum(axis=0))[stat]
                - scores_of(counts[f"{formula}_worst"].sum(axis=0))[stat]
            )
            diff = _stat(sums[f"{formula}_current"], stat) - _stat(sums[f"{formula}_worst"], stat)
            lo, hi = np.percentile(diff[np.isfinite(diff)], [2.5, 97.5])
            base = f"smsr_variants.{formula}.{stat}_gain_current_vs_worst"
            out[base] = round(float(point), 4)
            out[f"{base}_ci_low"] = round(float(lo), 4)
            out[f"{base}_ci_high"] = round(float(hi), 4)
    return out


def scores_of(total: np.ndarray) -> dict[str, float | None]:
    from app.models import ConfusionTable

    a, b, c, d = (int(x) for x in total)
    return scores(ConfusionTable(hits=a, false_alarms=b, misses=c, correct_negatives=d))


def run() -> dict[str, float | int]:
    with eval_smsr.COMMUNES.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    test = {r["teryt"] for r in rows if r["zbior"] == "test"}
    cases, _ = eval_smsr.load_cases([r["teryt"] for r in rows if r["teryt"] in test])
    if not len(cases):
        return {}
    data = dense(cases, test)
    counts, _communes, usable, _obs = variant_counts(data)
    out = summarise(counts)
    out["smsr_variants.n_communes"] = len(
        {c for c, ok in zip(data["commune"], usable.any(axis=1), strict=True) if ok}
    )
    return out


if __name__ == "__main__":
    import json

    print(json.dumps(run(), ensure_ascii=False, indent=1, sort_keys=True))
