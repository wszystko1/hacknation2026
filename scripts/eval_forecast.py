"""Rolling validation of the exceedance forecast: `make eval ONLY=forecast`.

Weather 2001-2025 for the centroids of the 200 communes of demo/data/eval/gminy.csv (scripts/fetch_weather_history.py).
A case is a commune, an assessment date (1.V, 1.VI, 1.VII, 1.VIII), a test year Y in 2016-2025 and one crop group on
one soil category (drawn per commune and date from the combinations that still have a threshold after the date).
The label is whether KBW fell below the threshold in a period ending after the date, by the same code as the verdict.
A case of year Y sees only the years before Y: the analogs, the historical frequency and the GBDT training set.

Compared: completion with runs (the method of the app), the historical frequency (the reference), and LightGBM
(only here; the app keeps no model: forecast.gbdt_in_app is false). Skill is the Brier skill score against the
frequency, its interval comes from a bootstrap over commune-years. Needs data/raw/weather_history; without it the
evaluation is skipped and metrics.json keeps its previous values.
"""

from __future__ import annotations

import csv
import json
import random
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import NamedTuple

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.drought.kbw import period_dates  # noqa: E402
from app.drought.thresholds import threshold_mm  # noqa: E402
from app.forecast.exceedance import (  # noqa: E402
    MIN_YEARS,
    NO_READING,
    Daily,
    in_season_chances,
    own_weather_run,
    periods_after,
)
from app.models import SOIL_CATEGORIES, CropGroup  # noqa: E402

COMMUNES = ROOT / "demo" / "data" / "eval" / "gminy.csv"
HISTORY = ROOT / "data" / "raw" / "weather_history"
DATES = [(5, 1), (6, 1), (7, 1), (8, 1)]
TEST_YEARS = range(2016, 2026)
FIRST_YEAR = 2001
BINS = 10
BOOTSTRAP = 1000
SEED = 20260101


class Case(NamedTuple):
    teryt: str
    year: int
    asof: date
    crop: CropGroup
    soil: str
    lat: float
    lon: float


def load_series(path: Path) -> dict[date, tuple[float | None, float | None]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    first = date.fromisoformat(raw["start"])
    return {
        first + timedelta(i): (p, e)
        for i, (p, e) in enumerate(zip(raw["precipitation_mm"], raw["et0_mm"], strict=True))
    }


def draw_combination(teryt: str, month: int, day_: int) -> tuple[CropGroup, str] | None:
    """One crop group and soil category with a threshold after the date, fixed per commune and date."""
    asof = date(2021, month, day_)
    options = [
        (crop, soil)
        for crop in CropGroup
        if crop != CropGroup.INNA
        for soil in SOIL_CATEGORIES
        if periods_after(asof, crop, soil)
    ]
    return random.Random(f"{SEED}-{teryt}-{month}").choice(options) if options else None


def evaluate_case(daily: Daily, case: Case) -> tuple[float | None, float | None, bool | None]:
    """(chance by runs, historical frequency, what happened) for one case; only years before case.year feed the
    first two, the third is the weather of the case year itself."""
    years = [y for y in range(FIRST_YEAR, case.year) if y >= min(d.year for d in daily)]
    analog, own = in_season_chances(daily, case.asof, case.crop, case.soil, years)
    label = own_weather_run(
        daily, case.year, periods_after(case.asof, case.crop, case.soil), case.crop, case.soil
    )
    if analog.n < MIN_YEARS or own.n < MIN_YEARS or label is None:
        return None, None, None
    return analog.probability, own.probability, label


def features(daily: Daily, case: Case) -> list[float]:
    """Inputs of the comparison model: the state of the balance on the date, no history of other years."""
    periods = periods_after(case.asof, case.crop, case.soil)
    rows = []
    for n in (periods[0], periods[-1]):
        start, end = period_dates(case.year, n)
        known = [
            daily.get(start + timedelta(i), NO_READING) for i in range((min(end, case.asof) - start).days + 1)
        ]
        kbw = sum((p or 0) - (e or 0) for p, e in known)
        thr = float(threshold_mm(case.crop, case.soil, n))
        rows += [kbw - thr, float((end - case.asof).days), thr]
    recent = [daily.get(case.asof - timedelta(i), NO_READING) for i in range(30)]
    return [
        float(case.asof.timetuple().tm_yday), case.lat, case.lon, *rows,
        sum(p or 0 for p, _ in recent), sum(e or 0 for _, e in recent),
    ]  # fmt: skip


def brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def ece(p: np.ndarray, y: np.ndarray) -> float:
    """Expected calibration error over 10 equal bins: bin share times |mean forecast - observed share|."""
    which = np.minimum((p * BINS).astype(int), BINS - 1)
    return float(
        sum(abs(p[which == b].mean() - y[which == b].mean()) * (which == b).mean() for b in set(which))
    )


def calibration(p: np.ndarray, y: np.ndarray) -> list[dict]:
    which = np.minimum((p * BINS).astype(int), BINS - 1)
    out = []
    for b in range(BINS):
        m = which == b
        out.append(
            {"p": round(float(p[m].mean()), 3) if m.any() else None,
             "observed_pct": round(100 * float(y[m].mean()), 1) if m.any() else None, "n": int(m.sum())}
        )  # fmt: skip
    return out


def classification(p: np.ndarray, y: np.ndarray) -> dict[str, float]:
    """Accuracy, recall and precision for the answer "exceeded" at a chance of 50% or more."""
    said = p >= 0.5
    tp = float(np.sum(said & (y == 1)))
    return {
        "accuracy": float(np.mean(said == (y == 1))),
        "recall": tp / max(float(np.sum(y == 1)), 1.0),
        "precision": tp / max(float(np.sum(said)), 1.0),
    }


def bootstrap_skill(
    groups: np.ndarray, err_method: np.ndarray, err_ref: np.ndarray, rng: np.random.Generator
) -> tuple[float, float]:
    """95% interval of 1 - sum(method)/sum(reference), resampling commune-years as whole groups."""
    ids, inverse = np.unique(groups, return_inverse=True)
    sum_m = np.bincount(inverse, weights=err_method)
    sum_r = np.bincount(inverse, weights=err_ref)
    skills = []
    for _ in range(BOOTSTRAP):
        pick = rng.integers(0, len(ids), len(ids))
        skills.append(1 - sum_m[pick].sum() / sum_r[pick].sum())
    low, high = np.percentile(skills, [2.5, 97.5])
    return float(low), float(high)


def gbdt_predictions(rows: list[dict]) -> dict[int, float]:
    """LightGBM trained for each test year on the cases of earlier years only; {row index: chance}."""
    import lightgbm as lgb

    out: dict[int, float] = {}
    for year in TEST_YEARS:
        train = [r for r in rows if r["year"] < year and r["label"] is not None]
        test = [(i, r) for i, r in enumerate(rows) if r["year"] == year and r["p_analog"] is not None]
        params = {
            "objective": "binary", "learning_rate": 0.05, "num_leaves": 15, "min_data_in_leaf": 40,
            "bagging_fraction": 0.8, "bagging_freq": 1, "feature_fraction": 0.8, "seed": SEED,
            "num_threads": 2, "verbosity": -1,
        }  # fmt: skip
        data = lgb.Dataset(np.array([r["x"] for r in train]), np.array([int(r["label"]) for r in train]))
        model = lgb.train(params, data, num_boost_round=150)
        chance = model.predict(np.array([r["x"] for _, r in test]))
        out.update({i: float(c) for (i, _), c in zip(test, chance, strict=True)})
    return out


def commune_rows(c: dict) -> list[dict]:
    path = HISTORY / f"{c['teryt']}.json"
    if not path.is_file():
        return []
    daily = load_series(path)
    rows: list[dict] = []
    for month, day_ in DATES:
        combo = draw_combination(c["teryt"], month, day_)
        if combo is None:
            continue
        periods = None
        for year in range(FIRST_YEAR + 1, 2026):
            case = Case(c["teryt"], year, date(year, month, day_), *combo, float(c["lat"]), float(c["lon"]))
            periods = periods_after(case.asof, case.crop, case.soil)
            row = {
                "year": year,
                "teryt": c["teryt"],
                "p_analog": None,
                "p_hist": None,
                "x": features(daily, case),
            }
            row["label"] = own_weather_run(daily, year, periods, case.crop, case.soil)
            if year in TEST_YEARS:
                row["p_analog"], row["p_hist"], label = evaluate_case(daily, case)
                row["label"] = label if row["p_analog"] is not None else row["label"]
            rows.append(row)
    return rows


def collect() -> list[dict]:
    with COMMUNES.open(encoding="utf-8", newline="") as f:
        communes = list(csv.DictReader(f))
    with ProcessPoolExecutor(max_workers=8) as pool:
        return [row for rows in pool.map(commune_rows, communes, chunksize=4) for row in rows]


def run() -> dict:
    if not HISTORY.is_dir() or not any(HISTORY.glob("*.json")):
        print("no data/raw/weather_history: run scripts/fetch_weather_history.py first")
        return {}
    rows = collect()
    scored = [i for i, r in enumerate(rows) if r["p_analog"] is not None]
    if not scored:
        return {}
    gbdt = gbdt_predictions(rows)
    y = np.array([int(rows[i]["label"]) for i in scored], dtype=float)
    p_a = np.array([rows[i]["p_analog"] for i in scored])
    p_h = np.array([rows[i]["p_hist"] for i in scored])
    p_g = np.array([gbdt[i] for i in scored])
    groups = np.array([f"{rows[i]['teryt']}-{rows[i]['year']}" for i in scored])
    b_a, b_h, b_g = brier(p_a, y), brier(p_h, y), brier(p_g, y)
    low, high = bootstrap_skill(groups, (p_a - y) ** 2, (p_h - y) ** 2, np.random.default_rng(SEED))
    cls, cls_hist = classification(p_a, y), classification(p_h, y)
    base = float(y.mean())
    out = {
        "forecast.n_cases": len(scored),
        "forecast.n_communes": len({rows[i]["teryt"] for i in scored}),
        "forecast.test_year_first": TEST_YEARS[0],
        "forecast.test_year_last": TEST_YEARS[-1],
        "forecast.base_rate": round(base, 4),
        "forecast.brier": round(b_a, 4),
        "forecast.brier_hist": round(b_h, 4),
        "forecast.brier_gbdt": round(b_g, 4),
        "forecast.brier_skill": round(1 - b_a / b_h, 4),
        "forecast.brier_skill_ci_low": round(low, 4),
        "forecast.brier_skill_ci_high": round(high, 4),
        "forecast.bss_analog": round(1 - b_a / b_h, 4),
        "forecast.bss_gbdt": round(1 - b_g / b_h, 4),
        "forecast.ece_analog": round(ece(p_a, y), 4),
        "forecast.ece_gbdt": round(ece(p_g, y), 4),
        "forecast.gbdt_in_app": False,
        "forecast.accuracy_majority": round(max(base, 1 - base), 4),
        "forecast.calibration": calibration(p_a, y),
    }
    out |= {f"forecast.{k}": round(v, 4) for k, v in cls.items()}
    out |= {f"forecast.{k}_hist": round(v, 4) for k, v in cls_hist.items()}
    return out


# scripts/evaluate.py loads this file by path without registering it; the worker processes of `collect` need
# the functions to be importable by module name when they are pickled.
sys.modules.setdefault(__name__, SimpleNamespace(**globals()))

if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
