import json
from pathlib import Path

import pytest

from scripts.eval_smsr import strongest_baseline

A, C, P = "smsr.baseline_csi_always_drought", "smsr.baseline_csi_climatology", "smsr.baseline_csi_nasa_power_grid"


def test_power_grid_wins():
    assert strongest_baseline({A: 0.05, C: 0.07, P: 0.15}) == ("nasa_power_grid", 0.15)


def test_climatology_wins():
    assert strongest_baseline({A: 0.05, C: 0.2, P: 0.15}) == ("climatology", 0.2)


def test_always_drought_wins():
    assert strongest_baseline({A: 0.3, C: 0.2, P: 0.15}) == ("always_drought", 0.3)


def test_missing_power_grid_uses_the_other_two():
    assert strongest_baseline({A: 0.05, C: 0.07}) == ("climatology", 0.07)


def test_metrics_gain_is_csi_minus_strongest_line():
    m = json.loads((Path(__file__).resolve().parents[1] / "metrics.json").read_text())
    if "smsr.csi_gain_vs_baseline" not in m:
        pytest.skip("no smsr metrics")
    lines = [m[k] for k in (A, C, P) if k in m]
    assert m["smsr.csi_gain_vs_baseline"] == pytest.approx(m["smsr.csi"] - max(lines), abs=1e-9)
