"""IMGW archive index and the station-based weather chain, on excerpts of real archive files."""

import zipfile
from datetime import date

import pytest

from app.geodata import fetch_weather, imgw

from .conftest import fixture_text

GAUGE = "249180020"  # WARSZOWICE, rows of June 2025
SYNOP = "354150100"  # KOŁOBRZEG-DŹWIRZYNO, rows of 2023


def write_zip(path, member, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(member, text.encode("cp1250"))


@pytest.fixture
def archive():
    root = imgw.imgw_dir()
    write_zip(
        root / "opad" / "2025" / "2025_06_o.zip", "o_d_06_2025.csv", fixture_text("imgw_o_d_06_2025.csv")
    )
    folder = root / "synop" / "2023"
    folder.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(folder / "2023_100_s.zip", "w") as z:
        z.writestr("s_d_100_2023.csv", fixture_text("imgw_s_d_100_2023.csv").encode("cp1250"))
        z.writestr("s_d_t_100_2023.csv", fixture_text("imgw_s_d_t_100_2023.csv").encode("cp1250"))
    return imgw.build_index(2023, 2025)


def test_index_holds_gauge_precipitation_and_synoptic_et0(archive):
    assert [s[0] for s in archive["precip"]] == sorted([GAUGE, SYNOP])
    assert [s[0] for s in archive["et0"]] == [SYNOP]
    name, lon, lat = imgw.station_table()[GAUGE]
    near = imgw.lookup("precip", lat + 0.05, lon, date(2025, 6, 1), date(2025, 6, 3), max_km=40)
    assert near["values"] == [20.4, 5.3, 13.8]  # the three first rows of the gauge file
    assert near["stations"][0]["name"] == name and near["stations"][0]["km"] == pytest.approx(5.6, abs=0.3)
    whole = imgw.lookup("precip", lat, lon, date(2025, 6, 1), date(2025, 6, 30), max_km=5)["values"]
    assert whole[3] == 0.0  # 4 June: empty value with status 9 is a dry day
    assert imgw.lookup("precip", lat + 2.0, lon, date(2025, 6, 1), date(2025, 6, 3), max_km=40) is None


def test_station_et0_is_plausible_and_status_columns_are_read(archive):
    _, lon, lat = imgw.station_table()[SYNOP]
    winter = imgw.lookup("et0", lat, lon, date(2023, 1, 1), date(2023, 1, 10), max_km=10)["values"]
    summer = imgw.lookup("et0", lat, lon, date(2023, 6, 20), date(2023, 6, 29), max_km=10)["values"]
    assert all(0.0 <= v < 2.5 for v in winter) and all(1.5 < v < 8.0 for v in summer)
    rain = imgw.lookup("precip", lat, lon, date(2023, 1, 1), date(2023, 1, 2), max_km=10)["values"]
    assert rain == [4.0, 0.0]  # second day: value ".0" with status 9 means no precipitation, not missing


def test_weather_prefers_stations_when_the_archive_refuses(net, archive):
    net.fail["archive-api"] = 429
    _, lon, lat = imgw.station_table()[GAUGE]
    result = fetch_weather(lat, lon, date(2025, 6, 30), today=date(2025, 12, 1))
    data = result.data
    i = data.dates.index("2025-06-01")
    assert data.precipitation_mm[i : i + 3] == [20.4, 5.3, 13.8]
    assert data.precipitation_sources["imgw"] > 0 and data.precipitation_station == "WARSZOWICE"
    assert data.precipitation_station_km == pytest.approx(0.0, abs=1.0)
    assert 0 <= data.missing_share <= 1 and any("WARSZOWICE" in note for note in result.notes)


def test_weather_without_index_says_how_to_build_it(net):
    net.fail["archive-api"] = 429
    result = fetch_weather(52.1, 19.35, date(2026, 6, 20), today=date(2026, 11, 21))
    assert result.status == "fallback" and result.data.precipitation_provider == "nasa-power"
    assert result.data.et0_provider == "nasa-power" and "50 km" in result.data.grid
    assert any("imgw-sync" in note for note in result.notes)
