"""Agreement of the method's "below / above the threshold" with SMSR IUNG drought symbols.

Verification of a yes/no forecast: a 2x2 table (hits, false alarms, misses, correct negatives), CSI, POD,
FAR, Peirce skill score (POD - POFD) and the base rate of "+"; for the farmer also accuracy, balanced accuracy,
recall and precision for drought next to the accuracy of the trivial answer "always the more frequent answer".
Called by scripts/eval_smsr.py; the report only reads the results from metrics.json.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.fmt import dec
from app.models import Agreement, ConfusionTable


def confusion(pairs: Iterable[tuple[bool, bool]]) -> ConfusionTable:
    """pairs of (method says drought, SMSR says drought)."""
    a = b = c = d = 0
    for predicted, observed in pairs:
        if predicted and observed:
            a += 1
        elif predicted:
            b += 1
        elif observed:
            c += 1
        else:
            d += 1
    return ConfusionTable(hits=a, false_alarms=b, misses=c, correct_negatives=d)


def _ratio(num: int, den: int) -> float | None:
    return num / den if den else None


def scores(t: ConfusionTable) -> dict[str, float | None]:
    a, b, c, d = t.hits, t.false_alarms, t.misses, t.correct_negatives
    pod = _ratio(a, a + c)
    pofd = _ratio(b, b + d)
    total = a + b + c + d
    specificity = _ratio(d, b + d)
    return {
        "csi": _ratio(a, a + b + c),
        "pod": pod,
        "far": _ratio(b, a + b),
        "peirce": pod - pofd if pod is not None and pofd is not None else None,
        "base_rate": _ratio(a + c, total),
        "accuracy": _ratio(a + d, total),
        "balanced_accuracy": (pod + specificity) / 2 if pod is not None and specificity is not None else None,
        "recall": pod,
        "precision": _ratio(a, a + b),
        "accuracy_majority": _ratio(max(a + c, b + d), total),
    }


BUCKETS: list[tuple[str, float, float]] = [
    ("0–10 mm", 0, 10),
    ("10–25 mm", 10, 25),
    ("25–50 mm", 25, 50),
    (">50 mm", 50, float("inf")),
]


def bucket_of(margin_mm: float) -> str:
    distance = abs(margin_mm)
    return next(name for name, lo, hi in BUCKETS if lo <= distance < hi)


def agreement_frame(metrics: dict[str, Any], margin_mm: float | None) -> Agreement:
    """The agreement frame of the report, from metrics.json; "available" is False until `make eval` ran."""
    csi = metrics.get("smsr.csi")
    if csi is None:
        return Agreement(
            available=False,
            sentence="Brak: zgodność metody z oceną SMSR, bo jeszcze jej nie zmierzyliśmy na gminach testowych.",
            base_rate=metrics.get("smsr.base_rate"),
            n_gmina_years=metrics.get("smsr.n_gmina_years"),
        )
    bucket = bucket_of(margin_mm) if margin_mm is not None else ""
    share = metrics.get(f"smsr.agreement_by_distance.{bucket}") if bucket else None
    k = round(100 * share) if share is not None else None
    sentence = (
        f"Przy takiej odległości od progu metoda zgadzała się z SMSR w {k} na 100 przypadków."
        if k is not None
        else f"Metoda zgadzała się z SMSR: CSI {csi:.2f}."
    )
    table = _table_from(metrics)
    baselines = {name: metrics[key] for name, key in BASELINE_KEYS.items() if metrics.get(key) is not None}
    clim = baselines.get("klimatologia gminy")
    if clim is not None and csi <= clim:
        sentence += (
            f" Uwaga: sama klimatologia gminy zgadza się z SMSR nie gorzej (CSI {dec(clim, 2)} wobec {dec(csi, 2)}),"
            " więc metoda nie dodaje tu nic ponad dawne wyniki gminy."
        )
    return Agreement(
        available=True,
        sentence=sentence,
        k_per_100=k,
        distance_bucket=bucket,
        csi=csi,
        pod=metrics.get("smsr.pod"),
        far=metrics.get("smsr.far"),
        peirce=metrics.get("smsr.peirce"),
        base_rate=metrics.get("smsr.base_rate"),
        csi_gain_vs_baseline=metrics.get("smsr.csi_gain_vs_baseline"),
        n_gmina_years=metrics.get("smsr.n_gmina_years"),
        n_symbols=metrics.get("smsr.n_symbols"),
        table=table,
        baselines=baselines,
        accuracy=metrics.get("smsr.accuracy"),
        balanced_accuracy=metrics.get("smsr.balanced_accuracy"),
        recall=metrics.get("smsr.recall"),
        precision=metrics.get("smsr.precision"),
        accuracy_majority=metrics.get("smsr.accuracy_majority"),
    )


# reference line -> key in metrics.json (CSI of the line)
BASELINE_KEYS = {
    "zawsze susza": "smsr.baseline_csi_always_drought",
    "zawsze brak suszy": "smsr.baseline_csi_never_drought",
    "klimatologia gminy": "smsr.baseline_csi_climatology",
    "sama siatka NASA POWER": "smsr.baseline_csi_nasa_power_grid",
}


def _table_from(metrics: dict[str, Any]) -> ConfusionTable | None:
    keys = ("hits", "false_alarms", "misses", "correct_negatives")
    if any(metrics.get(f"smsr.{k}") is None for k in keys):
        return None
    return ConfusionTable(**{k: int(metrics[f"smsr.{k}"]) for k in keys})
