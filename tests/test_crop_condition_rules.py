"""Plant condition from NDVI curves: harvest, jargon, counts, bare soil, stale scenes and the report route."""

from __future__ import annotations

import re
from datetime import date, timedelta

import pytest

from app.crop_condition import classify_season, compare
from app.geodata import SceneIndex
from app.models import CropGroup
from tests.acceptance.helpers import DOBRCZ, GSM_TODAY, html, report

WINTER = [(60, 0.45), (130, 0.85), (160, 0.85), (190, 0.45), (196, 0.45), (197, 0.15), (273, 0.2)]
SPRING = [(60, 0.2), (130, 0.2), (160, 0.8), (190, 0.8), (220, 0.35), (221, 0.15), (273, 0.2)]
BARE = [(60, 0.15), (273, 0.18)]


def _ndvi(doy: int, knots: list[tuple[int, float]]) -> float:
    for (d0, v0), (d1, v1) in zip(knots, knots[1:], strict=False):
        if d0 <= doy <= d1:
            return v0 + (v1 - v0) * (doy - d0) / (d1 - d0)
    return knots[-1][1] if doy > knots[-1][0] else knots[0][1]


def curve(
    year: int, knots: list[tuple[int, float]], until: date | None = None, step: int = 5, clear: float = 0.9
) -> list[SceneIndex]:
    out, day, end = [], date(year, 3, 1), until or date(year, 9, 30)
    while day <= end:
        v = _ndvi(day.timetuple().tm_yday, knots)
        out.append(
            SceneIndex(f"S2_{day}", day.isoformat(), 0, 5.0, round(v, 3), round(0.5 * v - 0.1, 3), clear, 900)
        )
        day += timedelta(days=step)
    return out


HISTORY = {y: curve(y, SPRING) for y in (2019, 2020, 2021, 2022)}


def test_scene_after_a_sharp_fall_is_a_harvest_and_never_weaker() -> None:
    day = date(2024, 8, 20)  # a week after the fall in the knots (harvest on day 221 = 8 August)
    c = compare(curve(2024, SPRING, until=day), HISTORY, CropGroup.ZBOZA_JARE, day)
    assert c.harvest is True
    assert c.signal is None
    assert c.state == "ok"
    assert "nie ocenia stresu" in c.words
    assert c.scene_date is not None and c.scene_date <= day


def test_harvested_winter_crop_is_a_harvest_too() -> None:
    day = date(2024, 8, 10)
    history = {y: curve(y, WINTER) for y in (2020, 2021, 2022)}
    c = compare(curve(2024, WINTER, until=day), history, CropGroup.ZBOZA_OZIME, day)
    assert c.season_group == "ozime"
    assert c.harvest is True and c.signal is None


def test_ripening_over_a_long_gap_is_not_a_harvest() -> None:
    day = date(2024, 7, 25)
    sparse = curve(2024, SPRING, until=day, step=12)  # cloudy summer: a reading every 12 days
    c = compare(sparse, HISTORY, CropGroup.ZBOZA_JARE, day)
    assert c.harvest is False


def test_words_for_the_farmer_have_no_index_names_and_carry_the_count() -> None:
    day = date(2024, 6, 25)
    weaker = compare(curve(2024, [(60, 0.2), (130, 0.2), (160, 0.5), (190, 0.5), (273, 0.2)], until=day),
                     HISTORY, CropGroup.ZBOZA_JARE, day)  # fmt: skip
    normal = compare(curve(2024, SPRING, until=day), HISTORY, CropGroup.ZBOZA_JARE, day)
    assert (weaker.signal, normal.signal) == ("weaker", "normal")
    for c in (weaker, normal):
        assert "NDVI" not in c.words and "NDMI" not in c.words
        assert "4 porównywalnych" in c.words
        assert c.n_seasons == 4
        assert c.phase_days is not None and c.phase_days > 0
        assert c.scene_date is not None and (day - c.scene_date).days < 5


def test_bare_soil_is_a_group_and_a_stated_gap() -> None:
    assert classify_season(curve(2022, BARE)) == "gola_gleba"
    day = date(2024, 8, 1)
    c = compare(
        curve(2024, BARE, until=day), {y: curve(y, BARE) for y in (2020, 2021, 2022)}, CropGroup.INNA, day
    )
    assert c.state == "missing" and c.signal is None and c.season_group == "gola_gleba"
    assert re.match(r"Brak: .* bo ", c.words)


def test_spring_that_has_not_started_is_a_gap_not_bare_soil() -> None:
    day = date(2024, 4, 20)
    c = compare(curve(2024, SPRING, until=day), HISTORY, CropGroup.ZBOZA_JARE, day)
    assert c.state == "missing" and "jeszcze nie ruszyła" in c.words


def test_old_scene_is_a_gap_with_its_age() -> None:
    last_read = date(2024, 6, 1)
    readings = curve(2024, SPRING, until=last_read)
    newest = date.fromisoformat(readings[-1].date)
    c = compare(readings, HISTORY, CropGroup.ZBOZA_JARE, date(2024, 7, 20))
    assert c.state == "missing" and f"{(date(2024, 7, 20) - newest).days} dni" in c.words


def test_too_few_readings_of_the_season_say_how_many() -> None:
    day = date(2024, 6, 25)
    c = compare(curve(2024, SPRING, until=day)[-2:], HISTORY, CropGroup.ZBOZA_JARE, day)
    assert c.state == "missing" and "2 czyste zdjęcia" in c.words


def test_seasons_without_a_reading_at_the_phase_are_not_counted() -> None:
    day = date(2024, 6, 25)
    short = {y: curve(y, SPRING, until=date(y, 5, 20)) for y in (2019, 2020, 2021)}  # stop before the phase
    c = compare(curve(2024, SPRING, until=day), short, CropGroup.ZBOZA_JARE, day)
    assert c.state == "missing"
    assert c.n_seasons == 0


def test_grass_is_compared_by_its_highest_greenness_so_far() -> None:
    grass = [(60, 0.6), (120, 0.8), (150, 0.8), (151, 0.35), (175, 0.8), (273, 0.7)]
    poor = [(60, 0.5), (120, 0.55), (150, 0.55), (151, 0.3), (175, 0.55), (273, 0.5)]
    history = {y: curve(y, grass) for y in (2020, 2021, 2022)}
    day = date(2024, 7, 5)
    assert compare(curve(2024, grass, until=day), history, CropGroup.INNA, day).signal == "normal"
    assert compare(curve(2024, poor, until=day), history, CropGroup.INNA, day).signal == "weaker"


@pytest.mark.parametrize("params", [DOBRCZ, GSM_TODAY], ids=["dobrcz", "gora-swietej-malgorzaty"])
def test_report_row_is_a_dated_reading_or_a_stated_gap(params: dict) -> None:
    c = report(params).crop_condition
    page = html(params, widok="doradca")
    row = re.search(r'id="wiersz-satelita".*?</div>', page, re.S)
    assert row is not None and "Tu pojawi" not in row.group(0)
    if c.state == "ok":
        assert c.scene_date is not None
        assert c.scene_date.strftime("%d.%m.%Y") in c.words
    elif c.state == "missing":
        assert c.words.startswith("Brak:") and " bo " in c.words
        assert "Brak:" in row.group(0)
    assert report(params).verdict.state in {
        "below",
        "above",
        "no_threshold",
        "running",
        "out_of_season",
        "no_data",
    }
