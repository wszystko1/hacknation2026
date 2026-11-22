"""Placement check: the 30 m hit, the random boundary points, the repeatable outlets, the choice and the metrics file."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.advice import placement
from app.geodata import WaterFeature
from app.geodata.samples import load_sample

from .test_placement import OUTLINE, X0, Y0, make_grid

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ev = _load("eval_retention")
evaluate = _load("evaluate")

DEMO = [("040303_2.0002.189/13", "2023-07-20"), ("100403_2.0011.144", "2026-11-21")]


def _ditch(x: float) -> list[list[list[float]]]:
    return [[[x, Y0 - 20.0], [x, Y0 + 120.0]]]  # a ditch running north-south at easting x


def _synthetic():
    """A 100 m square falling 2% to the west with a 300 m margin grid; a ditch 20 m west of the boundary."""
    grid = make_grid()
    parcel = SimpleNamespace(id="synthetic", rings_2180=[OUTLINE])
    terrain = SimpleNamespace(grid=grid, catchment_grid=grid, lowest_outline_point_2180=None)
    ditch = WaterFeature("ditch", 20.0, 100.0, _ditch(X0 - 20.0))
    return parcel, terrain, SimpleNamespace(features=[ditch])


def test_hit_counts_up_to_30_m_from_the_ditch_outline() -> None:
    rings = _ditch(1000.0)
    assert ev.hit([1030.0, Y0 + 50.0], rings)
    assert ev.hit([970.0, Y0 + 50.0], rings)
    assert not ev.hit([1030.5, Y0 + 50.0], rings)
    assert ev.hit(
        [1000.0, Y0 + 120.0 + 30.0], rings
    )  # beyond the end of the segment: distance to the end point
    assert not ev.hit([1000.0, Y0 + 120.0 + 31.0], rings)
    assert not ev.hit(None, rings)
    assert not ev.hit([1000.0, Y0 + 50.0], [])


def test_the_hit_is_measured_to_the_segment_not_only_to_its_vertices() -> None:
    long_ditch = [[[0.0, 0.0], [200.0, 0.0]]]
    assert ev.hit([100.0, 29.0], long_ditch)  # 100 m from both vertices, 29 m from the segment


def test_random_points_are_100_per_parcel_seeded_and_on_the_boundary() -> None:
    a = ev.random_boundary_points(OUTLINE, seed="p1")
    assert len(a) == 100
    assert a == ev.random_boundary_points(OUTLINE, seed="p1")
    assert a != ev.random_boundary_points(OUTLINE, seed="p2")
    for x, y in a:
        on_edge = (
            x in (X0, X0 + 100.0) and Y0 <= y <= Y0 + 100.0 or y in (Y0, Y0 + 100.0) and X0 <= x <= X0 + 100.0
        )
        assert on_edge or ev.distance_to_rings([x, y], [OUTLINE]) < 1e-6
    assert ev.N_RANDOM == 100


def test_both_outlets_of_the_synthetic_parcel_are_on_the_west_side_and_repeat() -> None:
    parcel, terrain, _ = _synthetic()
    first = ev.outlet_points(parcel, terrain)
    assert first == ev.outlet_points(parcel, terrain)
    for point in first.values():
        assert point is not None and point[0] == pytest.approx(X0, abs=10.0)


@pytest.mark.parametrize(("pid", "day"), DEMO)
def test_saved_demo_parcels_give_the_same_outlets_every_time(pid, day, monkeypatch) -> None:
    monkeypatch.setenv("GEODATA_OFFLINE", "1")
    sample = load_sample(pid, day)
    parcel, terrain = sample.parcel.data, sample.terrain.data
    first = ev.outlet_points(parcel, terrain)
    again = ev.outlet_points(load_sample(pid, day).parcel.data, load_sample(pid, day).terrain.data)
    assert first == again
    assert first["lowest"] is not None
    assert (
        ev.distance_to_rings(first["lowest"], [parcel.rings_2180[0]]) < 6.0
    )  # on the outline, rounded to 0.1 m


def test_the_third_saved_parcel_is_the_synthetic_one_and_repeats() -> None:
    parcel, terrain, water = _synthetic()
    one = ev.measure_ditches([(parcel, terrain, water)])
    assert one == ev.measure_ditches([(parcel, terrain, water)])
    assert one["retention.outlet_hit_lowest"] == 1.0 and one["retention.outlet_hit_d8"] == 1.0
    assert one["retention.n_ditch_parcels"] == 1


def test_measure_ditches_counts_misses_and_the_random_share() -> None:
    parcel, terrain, water = _synthetic()
    far = SimpleNamespace(features=[WaterFeature("ditch", 400.0, 1.0, _ditch(X0 + 500.0))])
    pond = SimpleNamespace(features=[WaterFeature("water_body", 5.0, 1.0, _ditch(X0 - 5.0))])
    out = ev.measure_ditches([(parcel, terrain, water), (parcel, terrain, far), (parcel, terrain, pond)])
    assert out["retention.n_ditch_parcels"] == 3
    assert out["retention.outlet_hit_lowest"] == pytest.approx(
        1 / 3, abs=1e-4
    )  # only a ditch counts, not a pond
    # the ditch 20 m west of the west side is within 30 m of that side and of the corners' neighbourhoods
    assert 0.0 < out["retention.outlet_hit_random"] < out["retention.outlet_hit_lowest"] + 0.5


def test_ndmi_from_the_file_takes_part_in_the_choice(tmp_path) -> None:
    parcel, terrain, water = _synthetic()
    out = ev.measure_ditches([(parcel, terrain, water)], ndmi=0.5)
    assert out["retention.outlet_hit_ndmi"] == 0.5
    assert out["retention.outlet_hit_share"] == 1.0  # lowest 1.0 beats 0.5
    far = SimpleNamespace(features=[WaterFeature("ditch", 400.0, 1.0, _ditch(X0 + 500.0))])
    out = ev.measure_ditches([(parcel, terrain, far)], ndmi=0.5)
    assert out["retention.outlet_hit_share"] == 0.5  # lowest 0.0, d8 0.0, ndmi 0.5 wins
    metrics = tmp_path / "metrics.json"
    metrics.write_text(json.dumps({"retention": {"outlet_hit_ndmi": 0.7}}), encoding="utf-8")
    assert ev.previous_ndmi(metrics) == 0.7
    assert ev.previous_ndmi(tmp_path / "none.json") is None


SCORES = [
    {"lowest": 0.5, "d8": 0.5},  # tie: the base
    {"lowest": 0.4, "d8": 0.6},
    {"lowest": 0.4, "d8": 0.4, "ndmi": 0.4},
    {"lowest": 0.4, "d8": 0.5, "ndmi": 0.7},
    {"lowest": 0.8, "d8": 0.5, "ndmi": 0.7},
    {"lowest": 0.3, "d8": 0.6, "ndmi": 0.6},  # tie between D8 and NDMI: D8
]


@pytest.mark.parametrize("scores", SCORES)
def test_share_equals_the_score_of_the_variant_outlet_method_picks_after_the_write(
    scores, tmp_path, monkeypatch
) -> None:
    parcel, terrain, water = _synthetic()
    out = ev.measure_ditches([(parcel, terrain, water)])
    # replace the measured scores by the case, then write the file the way `make eval` does
    out |= {f"retention.outlet_hit_{k}": v for k, v in scores.items()}
    chosen = ev.choose(scores)
    share = scores[chosen]
    metrics = tmp_path / "metrics.json"
    monkeypatch.setattr(evaluate, "METRICS", metrics)
    evaluate.save(out | {"retention.outlet_hit_share": share})
    monkeypatch.setattr(placement, "METRICS_PATH", metrics)
    method = placement.outlet_method()
    assert method == chosen
    written = json.loads(metrics.read_text(encoding="utf-8"))["retention"]
    assert written["outlet_hit_share"] == written[f"outlet_hit_{method}"]


def test_the_measured_share_is_the_score_of_the_picked_variant(tmp_path, monkeypatch) -> None:
    parcel, terrain, water = _synthetic()
    out = ev.measure_ditches([(parcel, terrain, water)], ndmi=0.25)
    metrics = tmp_path / "metrics.json"
    monkeypatch.setattr(evaluate, "METRICS", metrics)
    evaluate.save(out)
    monkeypatch.setattr(placement, "METRICS_PATH", metrics)
    written = json.loads(metrics.read_text(encoding="utf-8"))["retention"]
    assert written["outlet_hit_share"] == written[f"outlet_hit_{placement.outlet_method()}"]


def test_evaluate_writes_metrics_after_each_evaluation(tmp_path, monkeypatch) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "eval_first.py").write_text('def run():\n    return {"first.value": 7}\n', encoding="utf-8")
    (scripts / "eval_second.py").write_text(
        "import json\n"
        "from pathlib import Path\n"
        "def run():\n"
        f"    seen = json.loads(Path({str(tmp_path / 'metrics.json')!r}).read_text(encoding='utf-8'))\n"
        '    return {"second.sees_first": seen["first"]["value"]}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(evaluate, "ROOT", tmp_path)
    monkeypatch.setattr(evaluate, "METRICS", tmp_path / "metrics.json")
    repo_metrics = ROOT / "metrics.json"
    before = repo_metrics.read_bytes() if repo_metrics.is_file() else None
    assert evaluate.main(["first", "second", "missing"]) == 0
    data = json.loads((tmp_path / "metrics.json").read_text(encoding="utf-8"))
    assert data == {"first": {"value": 7}, "second": {"sees_first": 7}}
    assert (repo_metrics.read_bytes() if repo_metrics.is_file() else None) == before


def test_the_evaluation_list_ends_with_the_placement_checks() -> None:
    assert evaluate.EVALUATIONS[-3:] == ["retention", "ponds", "wet_zones"]


def test_measure_places_needs_reports_and_returns_nothing_without_them() -> None:
    assert ev.measure_places([]) == {}
