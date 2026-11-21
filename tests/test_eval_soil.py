"""The soil-rule agreement with the IUNG map, on a hand-made example (no data/raw, no network)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("eval_soil", ROOT / "scripts" / "eval_soil.py")
eval_soil = importlib.util.module_from_spec(_spec)
sys.modules["eval_soil"] = eval_soil
_spec.loader.exec_module(eval_soil)

# (map category, sand, silt, clay) and the category the rule gives, worked out from the USDA triangle:
#   90/7/3 sand -> I; 80/12/8 loamy sand -> I; 60/28/12 sandy loam -> II; 40/45/15 loam -> III;
#   20/45/35 silty clay loam -> IV.
FIVE = [
    ("1", 90, 7, 3),  # rule I, map I: agree
    ("2", 80, 12, 8),  # rule I, map II: one apart
    ("2", 60, 28, 12),  # rule II, map II: agree
    ("1", 40, 45, 15),  # rule III, map I: two apart
    ("4", 20, 45, 35),  # rule IV, map IV: agree
]


def rows(spec):
    return [
        {"iung_category": c, "sand_pct": str(s), "silt_pct": str(si), "clay_pct": str(cl)}
        for c, s, si, cl in spec
    ]


def test_agreement_on_five_hand_checked_points() -> None:
    result = eval_soil.compare(rows(FIVE))
    assert result["soil.n_points"] == 5
    assert result["soil.category_agreement"] == 0.6
    assert result["soil.agreement_within_one"] == 0.8
    assert result["soil.agreement_with_neighbour"] >= result["soil.category_agreement"]


def test_cells_that_are_not_categories_are_skipped() -> None:
    masked = rows([("5", 90, 7, 3), ("11", 90, 7, 3), ("1", 90, 7, 3)])  # organic soil, forest, category I
    result = eval_soil.compare(masked)
    assert result["soil.n_points"] == 1
    assert result["soil.category_agreement"] == 1.0


def test_no_points_give_no_metrics(tmp_path, monkeypatch) -> None:
    assert eval_soil.compare([]) == {}
    monkeypatch.setattr(eval_soil, "POINTS", tmp_path / "missing.csv")
    assert eval_soil.run() == {}


def test_run_reads_the_csv(tmp_path, monkeypatch) -> None:
    path = tmp_path / "points.csv"
    path.write_text(
        "voivodeship,lon,lat,iung_category,sand_pct,silt_pct,clay_pct\n"
        "x,18.0,53.0,1,90,7,3\nx,18.1,53.1,2,60,28,12\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(eval_soil, "POINTS", path)
    result = eval_soil.run()
    assert result["soil.n_points"] == 2
    assert result["soil.category_agreement"] == 1.0
