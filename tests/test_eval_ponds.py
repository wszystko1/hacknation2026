"""The pond check: AUC arithmetic and the two ends of the score on synthetic grids (valley with a pond, plane)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from app.geodata import ElevationGrid

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("eval_ponds", ROOT / "scripts" / "eval_ponds.py")
ponds = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ponds)

N = 100
STEP = 10.0
X0, Y_TOP = 500_000.0, 600_000.0


def _grid(z: np.ndarray) -> ElevationGrid:
    return ElevationGrid(
        crs="EPSG:2180", x0=X0, y_top=Y_TOP, step_m=STEP, rows=N, cols=N,
        z=z.tolist(), inside=[[1] * N for _ in range(N)],
    )  # fmt: skip


def _xy() -> tuple[np.ndarray, np.ndarray]:
    cols, rows = np.meshgrid(np.arange(N), np.arange(N))
    return cols * STEP, (N - rows) * STEP  # distance east and north of the south-west corner


def _pond_ring(
    cx: float, cy: float, half: float = 25.0, half_x: float | None = None
) -> list[list[list[float]]]:
    x, y = X0 + cx, Y_TOP - N * STEP + cy
    w = half if half_x is None else half_x
    return [[[x - w, y - half], [x + w, y - half], [x + w, y + half], [x - w, y + half], [x - w, y - half]]]


def test_auc_counts_ties_as_half() -> None:
    assert ponds.auc([3.0, 4.0], [1.0, 2.0]) == 1.0
    assert ponds.auc([1.0, 2.0], [3.0, 4.0]) == 0.0
    assert ponds.auc([1.0, 1.0], [1.0, 1.0]) == 0.5
    assert ponds.auc([2.0, 0.0], [1.0]) == 0.5
    assert ponds.auc([], [1.0]) is None


def test_valley_pond_scores_above_random_places() -> None:
    x, y = _xy()
    # a slope to the south with a valley along x = 500 m, deepening to the south; the pond sits in the valley
    z = 0.02 * y + 3.0 * (1.0 - np.exp(-((x - 500.0) ** 2) / (2 * 40.0**2)))
    out = ponds.measure_ponds([(_grid(z), [_pond_ring(500.0, 400.0, half_x=5.0)])])
    assert out["retention.pond_auc_lowest"] > 0.9
    assert out["retention.pond_auc_d8"] > 0.9
    assert out["retention.n_ponds"] == 1
    assert out["retention.pond_auc"] == max(out["retention.pond_auc_lowest"], out["retention.pond_auc_d8"])


def test_pond_on_a_plane_is_not_singled_out_by_the_base() -> None:
    x, y = _xy()
    z = 0.01 * x + 0.02 * y
    out = ponds.measure_ponds([(_grid(z), [_pond_ring(450.0, 500.0)])])
    assert out["retention.pond_auc_lowest"] == pytest.approx(0.5, abs=0.1)


def test_random_places_are_the_same_with_the_seed_and_never_in_a_pond() -> None:
    x, y = _xy()
    z = 0.02 * y + 3.0 * (1.0 - np.exp(-((x - 500.0) ** 2) / (2 * 40.0**2)))
    sample = [(_grid(z), [_pond_ring(500.0, 400.0, half_x=5.0)])]
    assert ponds.measure_ponds(sample) == ponds.measure_ponds(sample)
    mask = ponds.pond_mask(sample[0][0], sample[0][1])
    assert 0 < mask.sum() < 10  # a strip of 10 by 50 m holds about 5 cells


def test_pond_auc_follows_the_variant_that_wins_the_choice() -> None:
    assert ponds.choose({"lowest": 0.7, "d8": 0.8}) == "d8"
    assert ponds.choose({"lowest": 0.8, "d8": 0.8, "ndmi": 0.8}) == "lowest"
    assert ponds.choose({"lowest": 0.7, "d8": 0.7, "ndmi": 0.9}) == "ndmi"


def test_nothing_is_written_without_ponds() -> None:
    x, y = _xy()
    assert ponds.measure_ponds([(_grid(0.02 * y + 0 * x), [])]) == {}
    assert ponds.measure_ponds([]) == {}
