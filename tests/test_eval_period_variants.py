"""The period-variant and soil-sensitivity evaluations: the logic on tiny arrays, no data files."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import eval_period_variants as pv  # noqa: E402
import eval_soil_sensitivity as ss  # noqa: E402


def test_worst_period_keeps_an_earlier_deficit_that_the_current_period_has_left() -> None:
    margin = np.array([[-10.0, 5.0, np.nan, 20.0]])
    assert pv.predictions(margin, worst=False).tolist() == [[True, False, False, False]]
    assert pv.predictions(margin, worst=True).tolist() == [
        [True, True, True, True]
    ]  # NaN is skipped, not "below"


def test_soil_flip_share_counts_only_cells_with_a_threshold_for_both_categories() -> None:
    margins = np.full((1, 4, 3), np.nan)  # (case, soil I..IV, period)
    margins[0, 0] = [-5.0, 5.0, 5.0]  # category I: below, above, above
    margins[0, 1] = [5.0, 5.0, np.nan]  # category II: no threshold in the last period
    share, count = ss.flip_matrix(margins, worst=False)
    assert count[0, 1] == 2 and share[0, 1] == 0.5  # period 1 flips, period 2 does not
    share_worst, _ = ss.flip_matrix(margins, worst=True)
    assert (
        share_worst[0, 1] == 1.0
    )  # I stays below after period 1 (worst), II is above: both valid periods flip
