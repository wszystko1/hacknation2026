"""K2: plants from Sentinel-2, compared only with past seasons of the same rotation group at the same growth phase,
or a stated gap. Harvest and mowing are not read as stress; the satellite never changes the verdict."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.geodata import SceneIndex
from app.models import CropGroup
from tests.acceptance.helpers import html, report

# NDVI knots (day of year, value) of one season; a pair of knots one day apart is a sharp drop.
WINTER = [(60, 0.45), (130, 0.85), (160, 0.85), (190, 0.45), (196, 0.45), (197, 0.15), (273, 0.2)]
LATE = [(60, 0.15), (155, 0.2), (195, 0.85), (255, 0.85), (273, 0.7)]
GRASS = [
    (60, 0.6),
    (120, 0.8),
    (150, 0.8),
    (151, 0.35),
    (175, 0.8),
    (210, 0.8),
    (211, 0.35),
    (235, 0.75),
    (273, 0.7),
]
GRASS_LATER_MOWING = [
    (60, 0.6),
    (120, 0.8),
    (165, 0.8),
    (166, 0.35),
    (190, 0.8),
    (225, 0.8),
    (226, 0.35),
    (273, 0.7),
]
BARE = [(60, 0.15), (273, 0.18)]


def spring(greenup: int = 130, peak: float = 0.8) -> list[tuple[int, float]]:
    """Spring crop: bare until green-up, 30 days of growth, 30 days of plateau, 30 days of ripening, harvest."""
    g = greenup
    return [(60, 0.2), (g, 0.2), (g + 30, peak), (g + 60, peak), (g + 90, 0.35), (g + 91, 0.15), (273, 0.2)]


def _ndvi(doy: int, knots: list[tuple[int, float]]) -> float:
    for (d0, v0), (d1, v1) in zip(knots, knots[1:], strict=False):
        if d0 <= doy <= d1:
            return v0 + (v1 - v0) * (doy - d0) / (d1 - d0)
    return knots[-1][1] if doy > knots[-1][0] else knots[0][1]


def curve(
    year: int,
    knots: list[tuple[int, float]],
    until: date | None = None,
    ndmi_shift: float = 0.0,
    clear: float = 0.95,
) -> list[SceneIndex]:
    """Clear readings every 5 days from 1 March to 30 September (or `until`); NDMI follows NDVI unless shifted."""
    out, day, end = [], date(year, 3, 1), until or date(year, 9, 30)
    while day <= end:
        ndvi = _ndvi(day.timetuple().tm_yday, knots)
        out.append(
            SceneIndex(
                scene_id=f"S2_{day.isoformat()}",
                date=day.isoformat(),
                days_from_target=0,
                cloud_cover_pct=5.0,
                ndvi=round(ndvi, 3),
                ndmi=round(0.5 * ndvi - 0.1 + ndmi_shift, 3),
                valid_fraction=clear,
                pixels=900,
            )  # fmt: skip
        )
        day += timedelta(days=5)
    return out


def history(**groups: list[int]) -> dict[int, list[SceneIndex]]:
    shapes = {"jare": spring(), "ozime": WINTER, "pozne": LATE, "tuz": GRASS_LATER_MOWING, "gola_gleba": BARE}
    return {y: curve(y, shapes[g]) for g, years in groups.items() for y in years}


MIXED = history(jare=[2018, 2020, 2022], ozime=[2019, 2023], pozne=[2021])


@pytest.mark.xfail(reason="not built yet", strict=False)
@pytest.mark.parametrize(
    ("knots", "group"),
    [(WINTER, "ozime"), (spring(), "jare"), (LATE, "pozne"), (GRASS, "tuz"), (BARE, "gola_gleba")],
)
def test_each_past_season_gets_a_rotation_group(knots: list[tuple[int, float]], group: str) -> None:
    from app.crop_condition import classify_season

    assert classify_season(curve(2021, knots)) == group


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_only_seasons_of_the_same_group_are_compared_and_counted() -> None:
    from app.crop_condition import compare

    day = date(2024, 6, 25)
    c = compare(curve(2024, spring(), until=day), MIXED, CropGroup.ZBOZA_JARE, day)
    assert c.state == "ok"
    assert c.season_group == "jare"
    assert c.n_seasons == 3
    assert c.signal == "normal"


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_fewer_than_three_comparable_seasons_say_so() -> None:
    from app.crop_condition import compare

    day = date(2024, 6, 25)
    c = compare(curve(2024, spring(), until=day), history(jare=[2020, 2022], ozime=[2019, 2021, 2023]),
                CropGroup.ZBOZA_JARE, day)  # fmt: skip
    assert c.state == "missing"
    assert c.n_seasons == 2
    assert c.signal is None
    assert "za mało porównywalnych lat" in f"{c.words} {c.reason}"


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_comparison_follows_the_growth_phase_not_the_calendar() -> None:
    from app.crop_condition import compare

    # Sown 15 days earlier: on 15 July it is ripening while earlier seasons are still green on that date,
    # but 82 days after green-up it looks exactly like them.
    day = date(2024, 7, 15)
    c = compare(curve(2024, spring(greenup=115), until=day), MIXED, CropGroup.ZBOZA_JARE, day)
    assert c.state == "ok"
    assert c.signal == "normal"


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_lower_greenness_at_the_same_phase_is_weaker_in_plain_words() -> None:
    from app.crop_condition import compare

    day = date(2024, 6, 25)
    current = curve(2024, spring(peak=0.55), until=day)
    c = compare(current, MIXED, CropGroup.ZBOZA_JARE, day)
    assert c.state == "ok"
    assert c.signal == "weaker"
    assert "słabsze" in c.words
    assert c.scene_date == date.fromisoformat(current[-1].date)
    for jargon in ("NDVI", "NDMI"):
        assert jargon not in c.words


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_moisture_index_counts_only_with_a_closed_canopy() -> None:
    from app.crop_condition import compare

    early = date(2024, 5, 20)  # 11 days after green-up: mostly bare soil
    open_canopy = compare(
        curve(2024, spring(), until=early, ndmi_shift=-0.3), MIXED, CropGroup.ZBOZA_JARE, early
    )
    assert open_canopy.signal != "weaker"
    closed = date(2024, 6, 25)  # plateau: closed canopy, same greenness, much drier leaves
    dry = compare(curve(2024, spring(), until=closed, ndmi_shift=-0.3), MIXED, CropGroup.ZBOZA_JARE, closed)
    assert dry.state == "ok"
    assert dry.signal == "weaker"


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_mowing_is_flagged_and_not_read_as_stress() -> None:
    from app.crop_condition import compare

    day = date(2024, 6, 3)  # just after the first cut; earlier seasons were cut two weeks later
    grass = history(tuz=[2019, 2020, 2021, 2022, 2023])
    # Grassland has no crop group of its own in the regulation.
    c = compare(curve(2024, GRASS, until=day), grass, CropGroup.INNA, day)
    assert c.harvest is True
    assert c.signal is None
    assert "nie ocenia stresu" in c.words


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_no_clear_scene_is_a_stated_gap() -> None:
    from app.crop_condition import compare
    from app.geodata.satellite import INNER_BUFFER_M, MIN_CLEAR_SHARE

    assert INNER_BUFFER_M == 10
    assert 0 < MIN_CLEAR_SHARE < 1
    day = date(2024, 6, 25)
    for current in ([], curve(2024, spring(), until=day, clear=MIN_CLEAR_SHARE / 2)):
        c = compare(current, MIXED, CropGroup.ZBOZA_JARE, day)
        assert c.state == "missing"
        assert c.signal is None
        assert c.reason


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_report_and_pdf_say_the_plant_assessment_is_in_progress_or_give_the_scene_date() -> None:
    c = report().crop_condition
    assert c.state in {"waiting", "ok"}
    printed = html(path="/raport/druk")
    if c.state == "waiting":
        assert "ocena roślin w toku" in c.words
        assert "ocena roślin w toku" in printed
    else:
        assert c.scene_date is not None
        assert c.ndvi_spread is not None
        assert c.scene_date.strftime("%d.%m.%Y") in printed


def test_satellite_never_changes_the_verdict() -> None:
    r = report()
    assert r.crop_condition.state in {"ok", "missing", "waiting"}
    if r.crop_condition.state == "missing":
        assert r.crop_condition.reason
    assert r.verdict.state in {"below", "above", "no_threshold", "running", "out_of_season", "no_data"}
