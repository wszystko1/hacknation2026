"""Agreement of the method's "below / above the threshold" with SMSR IUNG drought symbols.

Verification of a yes/no forecast: a 2x2 table (hits, false alarms, misses, correct negatives), CSI, POD,
FAR, Peirce skill score (POD - POFD) and the base rate of "+". Called by scripts/eval_smsr.py; the report
only reads the results from metrics.json.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

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
    return {
        "csi": _ratio(a, a + b + c),
        "pod": pod,
        "far": _ratio(b, a + b),
        "peirce": pod - pofd if pod is not None and pofd is not None else None,
        "base_rate": _ratio(a + c, a + b + c + d),
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
            sentence="Tu pojawi się zgodność metody z oceną SMSR, zmierzona na gminach testowych.",
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
    )
