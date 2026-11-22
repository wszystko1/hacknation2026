"""Scene choice for the plant assessment: the largest clear share within 20 days wins; no scene, one plain line."""

from __future__ import annotations

import json
from datetime import date, timedelta

from app.crop_condition import compare
from app.crop_condition.background import _decode, frozen_path
from app.crop_condition.compare import CLOUDY, choose_scene
from app.crop_condition.rotation import usable_points
from app.geodata import SceneIndex
from app.models import CropGroup


def _scene(day: date, share: float, ndvi: float = 0.7) -> SceneIndex:
    return SceneIndex(
        scene_id=f"s-{day}", date=day.isoformat(), days_from_target=0, cloud_cover_pct=10.0,
        ndvi=ndvi, ndmi=0.2, valid_fraction=share, pixels=100,
    )  # fmt: skip


def _frozen(parcel_id: str) -> dict:
    return _decode(json.loads(frozen_path(parcel_id).read_text(encoding="utf-8"))["seasons"])


DAY = date(2023, 7, 20)


def test_the_clearest_of_several_clean_scenes_wins() -> None:
    readings = [_scene(DAY - timedelta(days=d), s) for d, s in ((15, 0.9), (8, 0.6), (2, 0.8))]
    chosen = choose_scene(usable_points(readings), DAY)
    assert chosen[-1].day == DAY - timedelta(days=15)


def test_a_tie_goes_to_the_nearest_scene() -> None:
    readings = [_scene(DAY - timedelta(days=d), 1.0) for d in (15, 3)]
    assert choose_scene(usable_points(readings), DAY)[-1].day == DAY - timedelta(days=3)


def test_one_clean_scene_is_the_one_used() -> None:
    readings = [_scene(DAY - timedelta(days=d), s) for d, s in ((12, 0.19), (6, 0.7), (1, 0.3))]
    points = usable_points(readings)
    assert [p.scene.valid_fraction for p in points] == [0.7]
    assert choose_scene(points, DAY)[-1].day == DAY - timedelta(days=6)


def test_scenes_older_than_the_window_do_not_compete() -> None:
    readings = [_scene(DAY - timedelta(days=30), 1.0), _scene(DAY - timedelta(days=5), 0.6)]
    assert choose_scene(usable_points(readings), DAY)[-1].day == DAY - timedelta(days=5)


def test_no_clean_scene_gives_the_plain_reason() -> None:
    readings = [_scene(DAY - timedelta(days=d), 0.19) for d in (14, 6, 1)]
    result = compare(readings, {}, list(CropGroup)[0], DAY)
    assert result.state == "missing"
    assert result.reason == CLOUDY == "zbyt wiele chmur na zdjęciach z tego okresu"
    assert result.scene_date is None


def test_frozen_dobrcz_season_assesses_on_a_clean_scene() -> None:
    seasons = _frozen("040303_2.0002.189/13")
    points = choose_scene([p for p in usable_points(seasons[2023]) if p.day <= DAY], DAY)
    assert points[-1].scene.valid_fraction >= 0.5
    assert points[-1].day == date(2023, 7, 6)  # the 14 July scene has 2% clear pixels
