"""Plausibility checks (app/geodata/sanity.py): boundaries, obviously wrong values, no guessing."""

from __future__ import annotations

import numpy as np
import pytest

from app.geodata import sanity
from app.geodata.sanity import Level

SQUARE = [
    [
        [500000.0, 400000.0],
        [500100.0, 400000.0],
        [500100.0, 400100.0],
        [500000.0, 400100.0],
        [500000.0, 400000.0],
    ]
]


def test_slope_boundaries_and_the_live_error() -> None:
    assert sanity.check_slope(0.0).level is Level.OK
    assert sanity.check_slope(40.0).level is Level.OK
    assert sanity.check_slope(40.01).level is Level.INVALID
    assert sanity.check_slope(-0.1).level is Level.INVALID
    live = sanity.check_slope(148.9, 1939.24)
    assert live.level is Level.INVALID
    assert live.missing_text.startswith("brak: spadek")
    assert "nasz" not in live.reason


@pytest.mark.parametrize("bad", [None, float("nan"), float("inf")])
def test_slope_missing_or_not_a_number_is_invalid(bad) -> None:
    assert sanity.check_slope(bad).level is Level.INVALID


def test_slope_on_too_few_valid_cells_is_invalid() -> None:
    assert sanity.check_slope(3.0, 5.0, 0.49).level is Level.INVALID
    assert sanity.check_slope(3.0, 5.0, 0.5).level is Level.OK


def test_slope_consistency_warns_only_on_a_big_gap() -> None:
    assert sanity.check_slope_consistency(3.0, 2.5).level is Level.OK
    assert sanity.check_slope_consistency(None, 2.0).level is Level.OK
    assert sanity.check_slope_consistency(25.0, 2.0).level is Level.WARNING
    assert sanity.check_slope_consistency(12.0, 8.0).level is Level.OK  # gap below 10 points


def test_plane_slope_of_a_tilted_grid() -> None:
    z = np.fromfunction(lambda r, c: 100.0 - 0.03 * 10.0 * c, (10, 10))
    assert sanity.plane_slope_pct(z, np.ones((10, 10), bool), 10.0) == pytest.approx(3.0, abs=0.01)
    assert sanity.plane_slope_pct(z, np.zeros((10, 10), bool), 10.0) is None


def test_nodata_markers_and_zero_gaps_become_nan() -> None:
    z = np.array([[250.0, -9999.0], [0.0, 251.0]])
    out = sanity.mask_nodata(z)
    assert np.isnan(out[0, 1]) and np.isnan(out[1, 0])
    assert out[0, 0] == 250.0
    assert z[0, 1] == -9999.0  # the input is not changed


def test_zero_is_kept_on_low_coast_land() -> None:
    z = np.array([[0.0, 0.5], [1.0, 0.0]])
    assert np.isfinite(sanity.mask_nodata(z)).all()


def test_dem_boundaries() -> None:
    flat = np.full((10, 10), 100.0)
    assert sanity.check_dem(flat).level is Level.OK
    bad = flat.copy()
    bad[0, 0] = 2600.0
    assert sanity.check_dem(bad).level is Level.INVALID
    bad[0, 0] = -6.0
    assert sanity.check_dem(bad).level is Level.INVALID
    bad[0, 0] = -5.0
    assert sanity.check_dem(bad).level is not Level.INVALID
    relief = flat.copy()
    relief[0, 0] = 100.0 + sanity.DEM_RELIEF_WARN_M + 1
    assert sanity.check_dem(relief).level is Level.WARNING
    relief[0, 0] = 100.0 + sanity.DEM_RELIEF_INVALID_M + 1
    assert sanity.check_dem(relief).level is Level.INVALID


def test_dem_nodata_share() -> None:
    z = np.full((10, 10), 100.0)
    z.flat[:11] = np.nan  # 11 %
    assert sanity.check_dem(z).level is Level.WARNING
    z.flat[:50] = np.nan
    assert sanity.check_dem(z).level is Level.INVALID
    assert "50%" in sanity.check_dem(z).reason


def test_dem_judges_gaps_by_the_outline_not_the_whole_grid() -> None:
    z = np.full((10, 10), 100.0)
    z[:, 5:] = np.nan  # border: half of the grid has no model
    inside = np.zeros((10, 10), bool)
    inside[3:7, 1:4] = True
    assert sanity.check_dem(z, inside).level is Level.WARNING
    inside[3:7, 5:8] = True
    assert sanity.check_dem(z, inside).level is Level.INVALID


def test_precipitation_and_et0_ranges() -> None:
    assert sanity.check_precipitation([0.0, 12.0, 300.0, None]).level is Level.OK
    assert sanity.check_precipitation([0.0, -0.1]).level is Level.INVALID
    assert sanity.check_precipitation([300.1]).level is Level.INVALID
    assert sanity.check_et0([0.0, 15.0]).level is Level.OK
    assert sanity.check_et0([99.0]).level is Level.INVALID
    assert sanity.check_et0([-1.0]).level is Level.INVALID


def test_clean_series_turns_wrong_days_into_gaps_without_correcting() -> None:
    assert sanity.clean_series([1.0, -2.0, 99.0, None, 3.0], 0.0, 15.0) == [1.0, None, None, None, 3.0]
    assert sanity.clean_series([float("nan")], 0.0, 15.0) == [None]


def test_series_gap_threshold_equals_the_regulation_code() -> None:
    from app.drought.kbw import MAX_MISSING_SHARE

    assert sanity.MISSING_SHARE_MAX == MAX_MISSING_SHARE
    assert sanity.check_series_gaps(0.10).level is Level.OK
    assert sanity.check_series_gaps(0.101).level is Level.WARNING
    assert "niekompletny" in sanity.check_series_gaps(0.5).reason
    assert sanity.check_series_gaps(1.5).level is Level.INVALID


def test_outline_boundaries() -> None:
    assert sanity.check_outline(SQUARE, 1.0).level is Level.OK
    assert sanity.check_outline([], 1.0).level is Level.INVALID
    line = [[[500000.0, 400000.0], [500100.0, 400000.0], [500200.0, 400000.0], [500000.0, 400000.0]]]
    zero = sanity.check_outline(line, 0.0)
    assert zero.level is Level.INVALID and "zero" in zero.reason
    open_ring = [SQUARE[0][:-1] + [[500000.0, 400050.0]]]
    assert sanity.check_outline(open_ring).level is Level.INVALID
    abroad = [[[x - 480000, y - 300000] for x, y in SQUARE[0]]]
    assert "Polski" in sanity.check_outline(abroad).reason
    assert sanity.check_outline(SQUARE, float("nan")).level is Level.INVALID


def test_outline_area_limits() -> None:
    tiny = [
        [
            [500000.0, 400000.0],
            [500001.0, 400000.0],
            [500001.0, 400001.0],
            [500000.0, 400001.0],
            [500000.0, 400000.0],
        ]
    ]
    assert sanity.check_outline(tiny).level is Level.INVALID  # 0.0001 ha
    huge = [
        [
            [500000.0, 400000.0],
            [550000.0, 400000.0],
            [550000.0, 450000.0],
            [500000.0, 450000.0],
            [500000.0, 400000.0],
        ]
    ]
    assert sanity.check_outline(huge).level is Level.INVALID  # 250 000 ha
    assert sanity.check_outline(SQUARE, 5000.0).level is Level.INVALID  # stated area disagrees with the range


def test_bow_tie_outline_is_a_warning() -> None:
    bow = [[[0.0, 0.0], [100.0, 100.0], [100.0, 0.0], [0.0, 100.0], [0.0, 0.0]]]
    shifted = [[[x + 500000, y + 400000] for x, y in bow[0]]]
    assert sanity.check_polygon_valid(shifted).level is Level.WARNING
    assert sanity.check_polygon_valid(SQUARE).level is Level.OK


def test_uldk_decoy_stays_with_the_transport_guard() -> None:
    from app.geodata import uldk_guard
    from app.geodata.errors import UpstreamError

    uldk_guard.reset()
    try:
        with pytest.raises(UpstreamError):
            uldk_guard._check_shape("0\nnot|a|parcel", geometry=True)
    finally:
        uldk_guard.reset()


def test_soil_category_and_source() -> None:
    assert sanity.check_soil_category("II", "iung").level is Level.OK
    assert sanity.check_soil_category("V", "iung").level is Level.INVALID
    assert sanity.check_soil_category("II", "wróżka").level is Level.INVALID
    assert sanity.check_soil_category(None, "brak").level is Level.OK
    assert sanity.check_soil_category(None, "soilgrids").level is Level.INVALID


def test_soil_texture() -> None:
    assert sanity.check_soil_texture(40.0, 40.0, 20.0).level is Level.OK
    assert sanity.check_soil_texture(40.0, 40.0, None).level is Level.INVALID
    assert sanity.check_soil_texture(120.0, -10.0, -10.0).level is Level.INVALID
    assert sanity.check_soil_texture(10.0, 10.0, 10.0).level is Level.INVALID


def test_indices_and_clear_pixels() -> None:
    assert sanity.check_indices(0.6, 0.2, 0.9).level is Level.OK
    assert sanity.check_indices(1.0, -1.0, 0.9).level is Level.OK
    assert sanity.check_indices(1.2, 0.2, 0.9).level is Level.INVALID
    assert sanity.check_indices(0.6, -1.01, 0.9).level is Level.INVALID
    assert sanity.check_indices(0.6, 0.2, 0.4).level is Level.WARNING
    assert sanity.check_indices(0.6, 0.2, 0.1).level is Level.INVALID
    assert sanity.check_indices(None, None, 0.9).level is Level.OK


def test_smsr_symbols() -> None:
    for symbol in "+-x#*n":
        assert sanity.check_smsr_symbol(symbol).level is Level.OK
    assert sanity.check_smsr_symbol("?").level is Level.INVALID
    assert sanity.check_smsr_symbol(None).level is Level.INVALID


def test_a_failing_check_is_a_gap_with_a_reason() -> None:
    def broken() -> sanity.Check:
        raise RuntimeError("boom")

    result = sanity.guarded("x", broken)
    assert result.level is Level.INVALID and "kontrola nie powiodła się" in result.reason
    assert sanity.guarded("slope", sanity.check_slope, "abc").level is Level.INVALID


def test_worst_and_notes() -> None:
    w, i = sanity.warn("a"), sanity.invalid("b")
    assert sanity.worst(sanity.ok(), w).level is Level.WARNING
    assert sanity.worst(w, i).level is Level.INVALID
    assert w.note == "Ostrzeżenie: a" and i.note == "brak: b" and sanity.ok().note == ""
