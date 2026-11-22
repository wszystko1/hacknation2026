"""Agreement with SMSR: the 2x2 table and its scores, the bootstrap by commune, the threshold shift, the frame."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import numpy as np
import pytest

from app.models import ConfusionTable
from app.smsr.parser import CommuneTable
from app.validation import measure
from app.validation.agreement import agreement_frame, confusion, scores

ROOT = Path(__file__).resolve().parents[1]


def _eval_module():
    spec = importlib.util.spec_from_file_location("eval_smsr", ROOT / "scripts" / "eval_smsr.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["eval_smsr"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_confusion_and_scores_on_a_hand_counted_example() -> None:
    pairs = [(True, True)] * 10 + [(True, False)] * 5 + [(False, True)] * 10 + [(False, False)] * 75
    t = confusion(pairs)
    assert (t.hits, t.false_alarms, t.misses, t.correct_negatives) == (10, 5, 10, 75)
    s = scores(t)
    assert s["csi"] == pytest.approx(10 / 25)
    assert s["pod"] == pytest.approx(0.5)
    assert s["far"] == pytest.approx(5 / 15)
    assert s["peirce"] == pytest.approx(0.5 - 5 / 80)
    assert s["base_rate"] == pytest.approx(0.2)
    assert s["accuracy"] == pytest.approx(0.85)
    assert s["balanced_accuracy"] == pytest.approx((0.5 + 75 / 80) / 2)
    assert s["precision"] == pytest.approx(10 / 15)
    assert s["accuracy_majority"] == pytest.approx(0.8)


def test_scores_without_any_drought_do_not_divide_by_zero() -> None:
    s = scores(ConfusionTable(hits=0, false_alarms=0, misses=0, correct_negatives=50))
    assert s["csi"] is None and s["pod"] is None and s["balanced_accuracy"] is None
    assert s["accuracy"] == 1.0 and s["accuracy_majority"] == 1.0


def test_bootstrap_draws_communes_not_symbols() -> None:
    # Commune A: 100 hits. Commune B: 100 false alarms. Drawing the 200 symbols would give CSI near 0.5 +- 0.07;
    # drawing the two communes gives 1 (AA), 0.5 (AB) or 0 (BB).
    counts = np.array([[100, 0, 0, 0], [0, 100, 0, 0]])
    low, high = measure.bootstrap_by_commune(counts, ["csi"], reps=500)["csi"]
    assert low < 0.1 and high > 0.9


def test_per_commune_counts_add_up() -> None:
    v = measure.View(
        commune=np.array(["a", "a", "b", "b"]),
        year=np.array([2020] * 4),
        observed=np.array([True, False, True, False]),
        margin={v: np.array([-5.0, 3.0, 4.0, -2.0]) for v in measure.VARIANTS},
        clim=np.zeros(4, dtype=bool),
    )
    counts = measure.per_commune_counts(v, v.margin["fao56"] < 0, ~np.isnan(v.margin["fao56"]), ["a", "b"])
    assert counts.tolist() == [[1, 0, 0, 1], [0, 1, 1, 0]]


def _table(symbols: dict[tuple[str, str, int], str]) -> CommuneTable:
    return CommuneTable(teryt="0000001", commune="Test", year=2021, cells=symbols)


def test_case_uses_kbw_of_the_period_against_the_regulation_threshold() -> None:
    # Period 1 (21.III-20.V, 61 days): no rain, 2 mm of ET0 a day gives KBW -122 mm; threshold -100 mm.
    gappy = [d.isoformat() for d in _days(2021) if d.month != 4]  # all of April missing: 30 of 61 days
    kbw = measure.period_kbw(gappy, [0.0] * len(gappy), [2.0] * len(gappy), 2021)
    assert 1 not in kbw  # more than 10% of the days without data: the period is left out
    full = [d.isoformat() for d in _days(2021)]
    kbw = measure.period_kbw(full, [0.0] * len(full), [2.0] * len(full), 2021)
    assert kbw[1] == pytest.approx(-122.0)
    cases = measure.Cases()
    table = _table({("Zboża ozime", "I", 1): "+", ("Zboża ozime", "II", 1): "-"})
    thresholds = {("zboza_ozime", "I", 1): -100.0, ("zboza_ozime", "II", 1): -150.0}
    series = {v: kbw for v in measure.VARIANTS}
    measure.add_commune_year(cases, table, series, thresholds)
    assert len(cases) == 2
    by_soil = {k[1]: (m, o) for k, m, o in zip(cases.key, cases.margin["fao56"], cases.observed, strict=True)}
    assert by_soil["I"] == (pytest.approx(-22.0), True)
    assert by_soil["II"] == (pytest.approx(28.0), False)


def _days(year: int):
    from datetime import date, timedelta

    d = date(year, 3, 1)
    while d <= date(year, 10, 31):
        yield d
        d += timedelta(days=1)


def _view(rows: list[tuple[int, float, bool]]) -> measure.View:
    n = len(rows)
    margin = np.array([r[1] for r in rows])
    return measure.View(
        commune=np.array(["c"] * n),
        year=np.array([r[0] for r in rows]),
        observed=np.array([r[2] for r in rows]),
        margin={v: margin.copy() for v in measure.VARIANTS},
        clim=np.zeros(n, dtype=bool),
    )


def test_threshold_shift_is_chosen_on_2020_2025_only() -> None:
    # Until 2025 the symbols agree with margin < 20 (shift +20 is best). 2026 would want a shift of -30.
    early = [(2022, m, m < 20) for m in range(-60, 61, 2)]
    late_a = [(2026, m, m < -30) for m in range(-60, 61, 2)]
    late_b = [(2026, m, m < 40) for m in range(-60, 61, 2)]
    shifts = []
    for late in (late_a, late_b):
        out = _eval_module().shift_keys(_view(early + late), 0.4, 0.6)  # interval without 1
        shifts.append(out["smsr.threshold_shift_mm"])
        assert "smsr.balanced_accuracy_2026_shifted" in out
    assert shifts[0] == shifts[1]
    assert 18 <= shifts[0] <= 21


def test_no_shift_when_the_interval_contains_one() -> None:
    assert _eval_module().shift_keys(_view([(2022, -5.0, True), (2026, 5.0, False)]), 0.8, 1.2) == {}


def test_choose_shift_prefers_no_shift_on_a_tie() -> None:
    v = _view([(2021, -10.0, True), (2021, 10.0, False)])
    assert measure.choose_shift(v, "fao56", [-3.0, 0.0, 3.0]) == 0.0


METRICS = {
    "smsr.csi": 0.38, "smsr.pod": 0.44, "smsr.far": 0.26, "smsr.peirce": 0.43, "smsr.base_rate": 0.05,
    "smsr.csi_gain_vs_baseline": 0.33, "smsr.n_gmina_years": 900, "smsr.n_symbols": 100000,
    "smsr.hits": 26, "smsr.false_alarms": 9, "smsr.misses": 34, "smsr.correct_negatives": 1093,
    "smsr.accuracy": 0.96, "smsr.balanced_accuracy": 0.71, "smsr.recall": 0.44, "smsr.precision": 0.74,
    "smsr.accuracy_majority": 0.95, "smsr.baseline_csi_climatology": 0.05,
    "smsr.baseline_csi_always_drought": 0.05, "smsr.baseline_csi_nasa_power_grid": 0.19,
    "smsr.agreement_by_distance.10–25 mm": 0.71, "smsr.calibration.dg.m25_m10.plus_share": 0.71,
}  # fmt: skip


def test_agreement_frame_fills_the_farmer_measures_the_table_and_the_reference_lines() -> None:
    a = agreement_frame(METRICS, -15.0)
    assert a.available and a.k_per_100 == 71 and a.distance_bucket == "10–25 mm"
    assert (a.accuracy, a.balanced_accuracy, a.recall, a.precision, a.accuracy_majority) == (
        0.96, 0.71, 0.44, 0.74, 0.95,
    )  # fmt: skip
    assert a.table is not None and a.table.hits == 26 and a.table.correct_negatives == 1093
    assert a.baselines["klimatologia gminy"] == 0.05 and a.baselines["sama siatka NASA POWER"] == 0.19
    assert "klimatologia" not in a.sentence  # the method beats it: nothing to warn about


def test_agreement_frame_says_so_when_climatology_is_not_worse() -> None:
    a = agreement_frame({**METRICS, "smsr.baseline_csi_climatology": 0.40}, -15.0)
    assert "klimatologia gminy" in a.sentence and re.search(r"0,40 wobec 0,38", a.sentence)


def test_agreement_frame_without_measurement_says_so() -> None:
    a = agreement_frame({}, None)
    assert not a.available and a.sentence.startswith("Brak:")
