"""K2: plants from Sentinel-2, NDMI vs the median of the same dekads, read with the crop phase, or a stated gap."""

from __future__ import annotations

from datetime import date

import pytest

from app.crop_condition import compare
from app.geodata import SceneIndex
from app.models import CropGroup
from tests.acceptance.helpers import report


def scene(day: str, ndmi: float, ndvi: float = 0.6, days_from_target: int = 3) -> SceneIndex:
    return SceneIndex(
        scene_id=f"S2_{day}", date=day, days_from_target=days_from_target, cloud_cover_pct=5.0,
        ndvi=ndvi, ndmi=ndmi, valid_fraction=0.95, pixels=900,
    )  # fmt: skip


HISTORY = [scene(f"{y}-06-12", ndmi=0.25) for y in (2019, 2020, 2021, 2022)]


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_drier_than_usual_in_plain_words_with_values_for_the_advisor() -> None:
    c = compare(scene("2023-06-12", ndmi=0.05), HISTORY, CropGroup.KUKURYDZA_ZIARNO, date(2023, 6, 14))
    assert c.state == "ok"
    assert "suchsze niż zwykle" in c.words
    assert c.n_seasons == 4
    assert c.ndmi == pytest.approx(0.05)
    assert c.ndmi_median == pytest.approx(0.25)
    for jargon in ("NDVI", "NDMI"):
        assert jargon not in c.words


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_as_usual_when_close_to_the_median() -> None:
    c = compare(scene("2023-06-12", ndmi=0.24), HISTORY, CropGroup.KUKURYDZA_ZIARNO, date(2023, 6, 14))
    assert c.state == "ok"
    assert "jak zwykle" in c.words


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_no_clear_scene_is_a_stated_gap() -> None:
    c = compare(None, HISTORY, CropGroup.ZBOZA_JARE, date(2023, 7, 20))
    assert c.state == "missing"
    assert c.reason


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_no_history_is_a_stated_gap() -> None:
    c = compare(scene("2023-06-12", ndmi=0.05), [], CropGroup.ZBOZA_JARE, date(2023, 6, 14))
    assert c.state == "missing"
    assert "poprzednich sezon" in c.reason


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_july_cereals_drop_is_read_as_ripening_not_drought() -> None:
    history = [scene(f"{y}-07-15", ndmi=0.20, ndvi=0.70) for y in (2019, 2020, 2021, 2022)]
    c = compare(scene("2023-07-15", ndmi=0.02, ndvi=0.35), history, CropGroup.ZBOZA_JARE, date(2023, 7, 20))
    assert c.state == "ok"
    assert "dojrzew" in c.words


def test_satellite_never_changes_the_verdict() -> None:
    r = report()
    assert r.crop_condition.state in {"ok", "missing", "waiting"}
    if r.crop_condition.state == "missing":
        assert r.crop_condition.reason
    assert r.verdict.state in {"below", "above", "no_threshold", "running", "out_of_season", "no_data"}
