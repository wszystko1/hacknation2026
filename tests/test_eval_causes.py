from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from scripts import eval_causes as ec


def series(years: range, rain, et0, missing_years: tuple[int, ...] = ()) -> ec.Series:
    """A daily series; `rain(year)` and `et0(year)` give the constant daily value of a year."""
    dates, p, e = [], [], []
    day = date(years[0], 1, 1)
    while day <= date(years[-1], 12, 31):
        dates.append(day.isoformat())
        p.append(None if day.year in missing_years else rain(day.year))
        e.append(None if day.year in missing_years else et0(day.year))
        day += timedelta(1)
    return dates, p, e


def case(period: int, cases: list[ec.Case], year: int) -> ec.Case:
    return next(c for c in cases if c.year == year and c.period == period)


def test_dry_year_raises_the_rain_flag_and_not_the_evaporation_flag():
    s = series(range(2001, 2013), lambda y: 0.5 if y == 2012 else 2.0, lambda y: 3.0)
    c = case(8, ec.commune_cases("T1", s, None, [2011, 2012]), 2012)
    assert c.flags[("rain", "fixed")] is True
    assert c.flags[("rain", "percentile")] is True
    assert c.flags[("evaporation", "fixed")] is False
    assert c.flags[("evaporation", "percentile")] is False


def test_normal_year_raises_no_flag():
    s = series(range(2001, 2013), lambda y: 2.0, lambda y: 3.0)
    c = case(8, ec.commune_cases("T1", s, None, [2012]), 2012)
    assert set(c.flags.values()) == {False}


def test_hot_year_raises_the_evaporation_flag():
    s = series(range(2001, 2013), lambda y: 2.0, lambda y: 5.0 if y == 2012 else 3.0)
    c = case(8, ec.commune_cases("T1", s, None, [2012]), 2012)
    assert c.flags[("evaporation", "fixed")] is True
    assert c.flags[("evaporation", "percentile")] is True
    assert c.flags[("rain", "fixed")] is False


def test_fixed_flag_matches_the_85_percent_boundary():
    # 1.7 mm a day against 2.0 usual is exactly 85%: the rule says "at most", so the flag is up
    s = series(range(2001, 2013), lambda y: 1.7 if y == 2012 else 2.0, lambda y: 3.0)
    c = case(8, ec.commune_cases("T1", s, None, [2012]), 2012)
    assert c.flags[("rain", "fixed")] is True
    s = series(range(2001, 2013), lambda y: 1.8 if y == 2012 else 2.0, lambda y: 3.0)
    assert case(8, ec.commune_cases("T1", s, None, [2012]), 2012).flags[("rain", "fixed")] is False


def test_too_few_earlier_seasons_give_no_flag_not_false():
    s = series(range(2001, 2004), lambda y: 0.1 if y == 2003 else 2.0, lambda y: 3.0)
    c = case(8, ec.commune_cases("T1", s, None, [2003]), 2003)
    assert c.flags[("rain", "fixed")] is None  # two earlier seasons: no usual season
    assert c.flags[("rain", "percentile")] is None
    assert ec.measures([c], ("rain", "fixed"), "spi", "k") == {}


def test_period_without_data_is_no_case():
    s = series(range(2001, 2013), lambda y: 2.0, lambda y: 3.0, missing_years=(2012,))
    assert ec.commune_cases("T1", s, None, [2012]) == []


def test_missing_earlier_years_do_not_count_as_dry_seasons():
    s = series(range(2001, 2013), lambda y: 2.0, lambda y: 3.0, missing_years=(2001, 2002, 2003))
    c = case(8, ec.commune_cases("T1", s, None, [2012]), 2012)
    assert c.flags[("rain", "percentile")] is False  # eight seasons left, the minimum
    s = series(range(2001, 2013), lambda y: 2.0, lambda y: 3.0, missing_years=(2001, 2002, 2003, 2004))
    assert case(8, ec.commune_cases("T1", s, None, [2012]), 2012).flags[("rain", "percentile")] is None


def test_spi_is_low_in_the_driest_year_and_none_without_data():
    s = series(range(2001, 2013), lambda y: 0.1 if y == 2012 else 1.0 + y / 1000, lambda y: 3.0)
    cases = ec.commune_cases("T1", s, None, [2012])
    assert case(8, cases, 2012).spi < ec.SPI_DRY
    thin = series(range(2001, 2013), lambda y: 1.0, lambda y: 3.0, missing_years=tuple(range(2001, 2012)))
    assert ec.empirical_spi({y: ec.window_rain(thin, y, 8) for y in range(2001, 2013)}) == {}


def make(flag: bool | None, share: float | None, spi: float | None = None) -> ec.Case:
    return ec.Case("T", 2020, 5, {("rain", "fixed"): flag}, spi, share)


def test_two_by_two_table_and_scores():
    cases = [make(True, 1.0)] * 3 + [make(True, 0.0)] * 1 + [make(False, 1.0)] * 1 + [make(False, 0.0)] * 5
    out = ec.measures(cases, ("rain", "fixed"), "smsr", "p")
    assert (out["p.hits"], out["p.false_alarms"], out["p.misses"], out["p.correct_negatives"]) == (3, 1, 1, 5)
    assert out["p.n"] == 10
    assert out["p.pod"] == 0.75
    assert out["p.far"] == 0.25
    assert out["p.csi"] == 0.6
    assert out["p.balanced_accuracy"] == pytest.approx((0.75 + 5 / 6) / 2, abs=1e-4)
    assert out["p.flag_rate"] == 0.4


def test_cases_without_flag_or_reference_are_left_out():
    cases = [make(True, 1.0), make(None, 1.0), make(True, None), make(False, 0.0)]
    out = ec.measures(cases, ("rain", "fixed"), "smsr", "p")
    assert out["p.n"] == 2


def test_no_pairs_gives_no_keys_and_a_measure_without_denominator_is_absent():
    assert ec.measures([], ("rain", "fixed"), "smsr", "p") == {}
    out = ec.measures([make(False, 0.0)] * 4, ("rain", "fixed"), "smsr", "p")
    assert out["p.correct_negatives"] == 4
    assert "p.pod" not in out and "p.far" not in out and "p.csi" not in out  # never 0 where undefined


def test_references():
    assert ec.reference_says_dry(make(True, 0.5), "smsr") is True
    assert ec.reference_says_dry(make(True, 0.2), "smsr") is False
    assert ec.reference_says_dry(make(True, 0.2), "smsr_any") is True
    assert ec.reference_says_dry(make(True, 0.0), "smsr_any") is False
    assert ec.reference_says_dry(make(True, None), "smsr_any") is None
    assert ec.reference_says_dry(make(True, 0.0, -1.5), "spi") is True
    assert ec.reference_says_dry(make(True, 0.0, -0.5), "spi") is False
    assert ec.reference_says_dry(make(True, 0.0, None), "spi") is None


def test_smsr_shares_count_only_plus_and_minus_cells():
    table = SimpleNamespace(
        cells={
            ("Zboża", "I", 5): "+",
            ("Zboża", "II", 5): "-",
            ("Zboża", "III", 5): "x",
            ("Rzepak", "I", 5): "+",
            ("Zboża", "I", 6): "x",
        }
    )
    assert ec.smsr_shares(table) == {5: pytest.approx(2 / 3)}


def test_snapshot_extends_the_history_after_2025_only():
    hist = {"start": "2025-12-30", "precipitation_mm": [1.0, 1.0], "et0_mm": [0.1, 0.1]}
    snap = {"start": "2025-12-31", "precipitation_mm": [9.0, 2.0, 3.0], "et0_mm": [9.0, 0.2, 0.3]}
    dates, rain, et0 = ec.merged_series(hist, snap)
    assert dates == ["2025-12-30", "2025-12-31", "2026-01-01", "2026-01-02"]
    assert rain == [1.0, 1.0, 2.0, 3.0]
    assert et0 == [0.1, 0.1, 0.2, 0.3]


def test_run_without_weather_history_gives_nothing(tmp_path):
    csv_path = tmp_path / "g.csv"
    csv_path.write_text("teryt,nazwa,wojewodztwo,lon,lat,zbior\n0204013,A,B,1,1,test\n", encoding="utf-8")
    assert ec.run(csv_path, tmp_path / "none", tmp_path, tmp_path) == {}
