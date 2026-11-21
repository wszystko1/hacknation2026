"""Agreement with SMSR IUNG. Until the archive for ~200 communes (data/raw/smsr) and their weather are in
place, this computes only what the labels alone give, on the committed sample demo/data/eval/smsr_sample.csv
(12 communes, 2020-2026, winter and spring cereals, real SMSR tables): the base rate of "+" and the CSI of
the two trivial baselines. The method's own CSI needs our KBW for each commune-year and is not written yet.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from app.validation.agreement import confusion, scores

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "demo" / "data" / "eval" / "smsr_sample.csv"


def labels(path: Path = SAMPLE) -> list[dict]:
    rows = [r for r in csv.DictReader(path.open(encoding="utf-8")) if r["symbol"] in {"+", "-"}]
    for r in rows:
        r["drought"] = r["symbol"] == "+"
    return rows


def climatology(rows: list[dict]) -> list[bool]:
    """Drought when, in the other years, the same commune, crop, category and period had "+" in >= half."""
    by_cell: dict[tuple, dict[str, bool]] = defaultdict(dict)
    for r in rows:
        by_cell[(r["teryt"], r["crop"], r["soil_category"], r["period"])][r["year"]] = r["drought"]
    out = []
    for r in rows:
        others = [
            v
            for y, v in by_cell[(r["teryt"], r["crop"], r["soil_category"], r["period"])].items()
            if y != r["year"]
        ]
        out.append(bool(others) and sum(others) >= len(others) / 2)
    return out


def run() -> dict[str, float | int]:
    rows = labels()
    if not rows:
        return {}
    observed = [r["drought"] for r in rows]
    always = scores(confusion((True, o) for o in observed))
    clim = scores(confusion(zip(climatology(rows), observed, strict=True)))
    return {
        "smsr.evaluated_on_sample": 1,
        "smsr.n_symbols": len(rows),
        "smsr.n_gmina_years": len({(r["teryt"], r["year"]) for r in rows}),
        "smsr.base_rate": round(always["base_rate"], 4),
        "smsr.baseline_csi_always_drought": round(always["csi"], 4),
        "smsr.baseline_csi_climatology": round(clim["csi"] or 0.0, 4),
    }
