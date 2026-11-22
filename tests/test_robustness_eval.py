"""The robustness evaluation (20 of the 50 sample parcels): the sample file, the date mix, the percentiles and the numbers it writes."""

from __future__ import annotations

import importlib.util
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sys.path.insert(0, str(ROOT / "scripts"))
ep = _load("eval_parcels")
ev = _load("eval_robustness")
ev.common = ep


def test_sample_file_has_50_rows_from_16_voivodeships_and_the_three_kinds_of_date() -> None:
    rows = ep.read_rows()
    assert len(rows) == 50
    assert len({r["wojewodztwo"] for r in rows}) == 16
    assert all(r["dzialka"] or (r["lon"] and r["lat"]) for r in rows)
    kinds = Counter(
        "dzis"
        if r["data"] == "dzis"
        else ("poza" if not (3, 21) <= (int(r["data"][5:7]), int(r["data"][8:])) <= (9, 30) else "sezon")
        for r in rows
    )
    assert kinds["sezon"] >= 20 and kinds["poza"] >= 5 and kinds["dzis"] >= 5
    dates = [date.fromisoformat(r["data"]) for r in rows if r["data"] != "dzis"]
    assert min(dates) >= date(2016, 1, 1) and max(dates) <= date(2026, 11, 21)


def test_the_sample_is_reproducible() -> None:
    assert ep.new_rows(today=date(2026, 11, 21)) == ep.new_rows(today=date(2026, 11, 21))


def test_percentiles() -> None:
    assert ep.percentile([1, 2, 3, 4, 5], 0.5) == 3
    assert ep.percentile([10.0], 0.95) == 10.0
    assert ep.percentile([1, 2, 3, 4, 5], 0.95) == pytest.approx(4.8)
    assert ep.percentile([], 0.5) == 0.0


def test_measure_writes_the_four_numbers(net, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ev, "WORK", tmp_path / "work")
    rows = [
        {
            "dzialka": "146501_1.0001.1",
            "wojewodztwo": "mazowieckie",
            "lon": "",
            "lat": "",
            "data": "2019-07-15",
            "uprawa": "zboza_jare",
        },
        {
            "dzialka": "",
            "wojewodztwo": "pomorskie",
            "lon": "19.1",
            "lat": "54.05",
            "data": "dzis",
            "uprawa": "kukurydza_ziarno",
        },
        {
            "dzialka": "226101_1.0001.100",
            "wojewodztwo": "pomorskie",
            "lon": "",
            "lat": "",
            "data": "2020-01-10",
            "uprawa": "rzepak",
        },
    ]
    result = ev.measure(rows, today=date(2026, 11, 21))
    assert result["robustness.n_parcels"] == 3
    assert result["robustness.report_ok_under_30s_share"] > 0
    assert 0 <= result["robustness.p50_s"] <= result["robustness.p95_s"] < 30
    # the fake ULDK names the same parcel (code 10) for the point; the other two ids give 14 and 22
    assert result["robustness.n_voivodeships"] == 3


def test_without_the_network_nothing_is_written(net, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ev, "WORK", tmp_path / "work")
    net.down = True
    rows = [
        {
            "dzialka": "146501_1.0001.1",
            "wojewodztwo": "mazowieckie",
            "lon": "",
            "lat": "",
            "data": "2019-07-15",
            "uprawa": "zboza_jare",
        }
    ]
    assert ev.measure(rows, today=date(2026, 11, 21)) == {}


def test_a_report_without_weather_is_built_but_not_ok(net, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ev, "WORK", tmp_path / "work")
    net.fail["archive-api"] = 429
    net.fail["power.larc"] = 500
    rows = [
        {
            "dzialka": "146501_1.0001.1",
            "wojewodztwo": "mazowieckie",
            "lon": "",
            "lat": "",
            "data": "2019-07-15",
            "uprawa": "zboza_jare",
        }
    ]
    result = ev.measure(rows, today=date(2026, 11, 21))
    assert result["robustness.report_ok_under_30s_share"] == 0
    assert result["robustness.n_no_weather"] == 1


def test_selection_is_deterministic_and_covers_every_voivodeship() -> None:
    rows = ep.read_rows()
    chosen = ev.select(rows)
    assert chosen == ev.select(rows)
    assert len(chosen) == 20
    assert len({r["wojewodztwo"] for r in chosen}) == len({r["wojewodztwo"] for r in rows}) == 16
    extra = chosen[16:]
    assert sum(r["data"] == "dzis" for r in extra) == 2
    assert (
        sum(
            r["data"] != "dzis" and not (3, 21) <= (int(r["data"][5:7]), int(r["data"][8:])) <= (9, 30)
            for r in extra
        )
        == 2
    )


def test_the_share_counts_only_reports_with_a_verdict_under_30_s(net, tmp_path, monkeypatch) -> None:
    from types import SimpleNamespace

    monkeypatch.setattr(ev, "WORK", tmp_path / "work")
    base = {"wojewodztwo": "mazowieckie", "lon": "", "lat": "", "data": "2019-07-15", "uprawa": "zboza_jare"}
    rows = [{**base, "dzialka": f"146501_1.0001.{i}"} for i in range(1, 5)]
    # per report: (state, seconds); the clock moves by that much between the two reads
    plan = iter([("ok", 5.0), ("ok", 31.0), ("no_data", 4.0), ("ok", 29.9)])
    now = [0.0]
    step = {"pending": 0.0}

    def clock() -> float:
        now[0] += step["pending"]
        step["pending"] = 0.0
        return now[0]

    def build(_req):
        state, seconds = next(plan)
        step["pending"] = seconds
        return SimpleNamespace(verdict=SimpleNamespace(state=state))

    result = ev.measure(rows, today=date(2026, 11, 21), clock=clock, build=build)
    assert result["robustness.report_ok_under_30s_share"] == 0.5  # reports 1 and 4
    assert result["robustness.n_no_weather"] == 1
    assert result["robustness.p50_s"] == 17.5


def test_sample_draws_points_and_asks_uldk_for_the_parcel(net, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ep, "CSV_PATH", tmp_path / "parcels.csv")
    asked: list[tuple[float, float]] = []

    def fake(lon: float, lat: float) -> str:
        asked.append((lon, lat))
        return "146501_1.0001.1"

    monkeypatch.setattr(ep, "parcel_of_point", fake)
    ep.sample()
    rows = ep.read_rows(tmp_path / "parcels.csv")
    assert len(rows) == 50 and asked
    assert any(r["dzialka"] == "146501_1.0001.1" for r in rows)  # the mazowieckie rows accept it


def test_one_script_writes_the_robustness_keys() -> None:
    import evaluate

    assert "robustness" in evaluate.EVALUATIONS and "parcels" not in evaluate.EVALUATIONS
    assert not hasattr(ep, "run")
