"""The report carries three separate answers, the reading, the vulnerability, the off-season part and the
second verdict variant; none of them is glued into one number."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.geodata.models import Satellite, SceneIndex, Weather, from_dict, to_jsonable
from app.models import CROP_LABELS, CROP_VERB, CropCondition, Report, Verdict
from tests.acceptance.helpers import DOBRCZ, GSM_TODAY, client, html, report

EXAMPLES = sorted((Path(__file__).resolve().parent.parent / "contracts" / "examples").glob("raport_*.json"))
GLUED = ("score", "risk", "risk_index", "ryzyko")


def keys(obj: object) -> set[str]:
    if isinstance(obj, dict):
        return set(obj) | {k for v in obj.values() for k in keys(v)}
    if isinstance(obj, list):
        return {k for v in obj for k in keys(v)}
    return set()


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_examples_validate_with_the_new_fields(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    for field in ("reading", "vulnerability", "off_season", "verdict_dg"):
        assert field in data, field
    r = Report.model_validate(data)
    assert not set(GLUED) & keys(r.model_dump(mode="json"))
    assert r.verdict.et_method == "fao56"


def test_report_has_no_glued_score() -> None:
    assert not set(GLUED) & keys(report().model_dump(mode="json"))


def test_every_crop_has_a_verb() -> None:
    assert set(CROP_VERB) == set(CROP_LABELS)
    assert set(CROP_VERB.values()) <= {"rosły", "rosła", "rósł"}


def test_verdict_defaults_to_fao56() -> None:
    v = Verdict(state="no_data", badge="", kbw_mm=None, threshold_mm=None, margin_mm=None, period=None,
                sentence="", how="")  # fmt: skip
    assert v.et_method == "fao56"


def test_plants_fields_default_to_no_reading() -> None:
    c = CropCondition(state="missing", words="Brak: zdjęcia, bo chmury")
    assert c.signal is None and c.season_group is None and c.harvest is False
    assert c.ndvi_spread is None and c.clear_share is None and c.phase_days is None


def test_today_the_plants_do_not_apply() -> None:
    r = report(GSM_TODAY)
    assert r.verdict.state == "out_of_season"
    assert r.crop_condition.state == "not_applicable"
    assert "nie dotyczy" in r.crop_condition.words


@pytest.mark.parametrize("path", ["/raport", "/raport/druk"])
@pytest.mark.parametrize("params", [DOBRCZ, GSM_TODAY], ids=["dobrcz", "gora-swietej-malgorzaty"])
def test_verdict_has_the_three_rows_and_no_placeholder(path: str, params: dict) -> None:
    page = html(params, path=path)
    top = page[page.index('id="werdykt"') :]
    top = top[: top.index("</section>")]
    assert 'id="wiersz-satelita"' in top
    assert 'id="wiersz-podatnosc"' in top
    assert "Tu pojawi" not in page


def test_reading_row_only_when_there_is_a_reading() -> None:
    page = html(DOBRCZ)
    r = report()
    assert ('id="wiersz-odczyt"' in page) is bool(r.reading)


def test_old_satellite_copies_still_load() -> None:
    old = {"target_date": "2023-07-20", "current": None, "history": [], "candidates": 0}
    sat = from_dict(Satellite, old)
    assert sat.seasons == {}
    scene = from_dict(SceneIndex, {"scene_id": "a", "date": "2023-07-01", "days_from_target": 1,
                                   "cloud_cover_pct": None, "ndvi": 0.5, "ndmi": 0.1,
                                   "valid_fraction": 0.9, "pixels": 40})  # fmt: skip
    assert scene.ndvi_spread is None


def test_seasons_survive_a_json_round_trip() -> None:
    scene = SceneIndex("a", "2021-06-01", 0, None, 0.6, 0.2, 0.9, 40, ndvi_spread=0.07)
    sat = Satellite(target_date="2023-07-20", current=None, seasons={2021: [scene]})
    back = from_dict(Satellite, json.loads(json.dumps(to_jsonable(sat))))
    assert back.seasons == {2021: [scene]}


def test_old_weather_copies_have_empty_temperature_and_sunshine() -> None:
    w = Weather(provider="x", latitude=1.0, longitude=2.0, dates=[], precipitation_mm=[], et0_mm=[])
    assert w.tmean_c == [] and w.sunshine_h == []


def test_api_serves_the_new_fields() -> None:
    r = client.get("/api/raport", params=DOBRCZ)
    assert r.status_code == 200
    body = r.json()
    assert {"reading", "vulnerability", "off_season", "verdict_dg"} <= set(body)
    assert body["vulnerability"]["reason"].startswith("Brak:") or body["vulnerability"]["sentence"]
