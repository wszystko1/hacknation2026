"""How often the verdict changes when the soil category is wrong: `make eval ONLY=soil_sensitivity`.

The threshold of the regulation depends on the soil category (I-IV), so a wrong category can move the verdict across
the line. On the "test" communes of demo/data/eval/gminy.csv (the ones of the `smsr.*` numbers) and the same years,
for every (commune, year, crop, analysis day = end of period n) where the regulation gives a threshold for both
categories, we compare the verdict "below / above the threshold" (FAO-56 balance, the variant of the report) at the
category a and at the category b:

  `cell`   the margin of period n only;
  `worst`  the smallest margin of periods 1..n, as the report picks the period (the verdict of the app).

Writes soil_sensitivity.*:
  flip_cell_pm1 / flip_worst_pm1   share of verdicts that change when the category is one step off (I-II, II-III,
                                   III-IV pairs, both directions, equal weight);
                                   (a flip between two categories does not depend on the direction);
  flip_cell_soilgrids / flip_worst_soilgrids
                                   the same flip rate weighted by the real errors of the soil rule: for every point of
                                   data/raw/soil_points/points.csv the map category (IUNG) is the "true" one and the
                                   category from SoilGrids texture is the "wrong" one (`category_from_texture`).
  n_pairs, n_cases                 pairs of categories and verdicts counted.
Needs data/raw (smsr, commune_weather, soil_points); without it `run()` returns nothing.
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
import eval_soil  # noqa: E402

from app.drought.kbw import PERIODS  # noqa: E402
from app.models import SOIL_CATEGORIES  # noqa: E402
from app.soil.texture import category_from_texture  # noqa: E402
from app.validation import measure  # noqa: E402

N_PERIODS = len(PERIODS)


def cube(cases: measure.Cases, communes: set[str]) -> np.ndarray:
    """Margins (FAO-56) as an array (commune-year-crop, soil I..IV, period); NaN where there is no threshold."""
    index: dict[tuple, int] = {}
    for c, y, (crop, _soil, _n) in zip(cases.commune, cases.year, cases.key, strict=True):
        if c in communes:
            index.setdefault((c, y, crop), len(index))
    out = np.full((len(index), len(SOIL_CATEGORIES), N_PERIODS), np.nan)
    for i, (c, y, (crop, soil, n)) in enumerate(zip(cases.commune, cases.year, cases.key, strict=True)):
        if c in communes:
            out[index[(c, y, crop)], SOIL_CATEGORIES.index(soil), n - 1] = cases.margin["fao56"][i]
    return out


def flip_matrix(margins: np.ndarray, worst: bool) -> tuple[np.ndarray, np.ndarray]:
    """(flip share, number of verdicts) for every ordered pair of categories (a true, b used), shape (4, 4)."""
    used = np.fmin.accumulate(margins, axis=2) if worst else margins
    below = used < 0
    valid = ~np.isnan(margins[:, :, :])  # period n must have a threshold for the category
    size = len(SOIL_CATEGORIES)
    share, count = np.zeros((size, size)), np.zeros((size, size), dtype=np.int64)
    for a in range(size):
        for b in range(size):
            both = valid[:, a, :] & valid[:, b, :]
            count[a, b] = both.sum()
            share[a, b] = (below[:, a, :] != below[:, b, :])[both].mean() if both.any() else np.nan
    return share, count


def pm1(share: np.ndarray, count: np.ndarray) -> float:
    """Count-weighted flip share over the neighbouring categories, both orders."""
    last = len(SOIL_CATEGORIES) - 1
    pairs = [(a, a + 1) for a in range(last)] + [(a + 1, a) for a in range(last)]
    total = sum(count[a, b] for a, b in pairs)
    return (
        float(sum(share[a, b] * count[a, b] for a, b in pairs if count[a, b]) / total)
        if total
        else float("nan")
    )


def soilgrids_weighted(share: np.ndarray, points: list[dict[str, str]]) -> float:
    """Mean flip share over the points: map category true, texture category used. Pairs a == b flip never."""
    values = []
    for row in points:
        if row["iung_category"] not in {"1", "2", "3", "4"}:
            continue
        true = int(row["iung_category"]) - 1
        used = SOIL_CATEGORIES.index(
            category_from_texture(float(row["sand_pct"]), float(row["silt_pct"]), float(row["clay_pct"]))[0]
        )
        values.append(0.0 if true == used else share[true, used])
    values = [v for v in values if not np.isnan(v)]
    return float(np.mean(values)) if values else float("nan")


def run() -> dict[str, float | int]:
    if not eval_soil.POINTS.is_file():
        return {}
    with eval_smsr.COMMUNES.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    test = {r["teryt"] for r in rows if r["zbior"] == "test"}
    cases, _ = eval_smsr.load_cases(sorted(test))
    if not len(cases):
        return {}
    margins = cube(cases, test)
    points = eval_soil.read_points()
    out: dict[str, float | int] = {"soil_sensitivity.n_points": len(points)}
    for name, worst in (("cell", False), ("worst", True)):
        share, count = flip_matrix(margins, worst)
        out[f"soil_sensitivity.flip_{name}_pm1"] = round(pm1(share, count), 4)
        out[f"soil_sensitivity.flip_{name}_soilgrids"] = round(soilgrids_weighted(share, points), 4)
        out[f"soil_sensitivity.n_{name}_pairs"] = int(sum(count[a, a + 1] for a in range(3)))
    return out


if __name__ == "__main__":
    import json

    print(json.dumps(run(), ensure_ascii=False, indent=1, sort_keys=True))
