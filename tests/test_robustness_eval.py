"""The 50-parcel evaluation: the sample file, the date mix, the percentiles and the numbers it writes."""

from __future__ import annotations

import importlib.util
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("eval_parcels", ROOT / "scripts" / "eval_parcels.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["eval_parcels"] = mod
    spec.loader.exec_module(mod)
    return mod


ev = _load()


def test_sample_file_has_50_rows_from_16_voivodeships_and_the_three_kinds_of_date() -> None:
    rows = ev.read_rows()
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
    assert ev.new_rows(today=date(2026, 11, 21)) == ev.new_rows(today=date(2026, 11, 21))


def test_percentiles() -> None:
    assert ev.percentile([1, 2, 3, 4, 5], 0.5) == 3
    assert ev.percentile([10.0], 0.95) == 10.0
    assert ev.percentile([1, 2, 3, 4, 5], 0.95) == pytest.approx(4.8)
    assert ev.percentile([], 0.5) == 0.0


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
