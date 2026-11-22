"""The report on several frozen parcels from different voivodeships, terrain, crops and dates.

Each location in demo/data/locations/<name>/ holds a frozen copy of every source (outline, weather, terrain, soil,
ditches, satellite indices, SMSR page). The tests build the report from it without a network and check what must
hold on every parcel: the numbers agree with each other, the badge follows the margin, the window follows the date,
no screen shows a forbidden phrase, retention actions have a place inside the outline or a reason.
`scripts/freeze_locations.py` rebuilds the copies.
"""

from __future__ import annotations

import functools
import json
import re
import time
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient

from app.advice.placement import PlaceCandidate, PlacementInput, find_places
from app.crop_condition import background
from app.geodata import config, load_sample
from app.main import app
from app.models import BADGE_ABOVE, BADGE_BELOW, Report
from app.smsr import pages
from app.soil import iung

ROOT = Path(__file__).resolve().parents[1] / "demo" / "data" / "locations"
LOCATIONS: list[dict] = json.loads((ROOT / "index.json").read_text(encoding="utf-8"))
NAMES = [loc["name"] for loc in LOCATIONS]
BY_NAME = {loc["name"]: loc for loc in LOCATIONS}

MAX_BUILD_S = 5.0
CAUSE_CODES = ("malo_opadu", "duze_parowanie", "gleba_lekka", "splyw", "faza_wrazliwa")
FLAT_SLOPE_PCT = 1.0
SLOPED_PCT = 5.0
MAX_DATA_LAG_DAYS = 10  # the IMGW station series ends a few days before the analysis date
TOO_SMALL = "za mały"
DITCH_NEAR_M = 50.0
SCREENS = {
    "farmer": ("/raport", {}),
    "print": ("/raport/druk", {}),
    "advisor": ("/raport", {"widok": "doradca"}),
}


@pytest.fixture
def use_location(monkeypatch: pytest.MonkeyPatch):
    """Point every frozen-copy reader at one location folder and keep the network shut."""

    def switch(name: str) -> dict:
        folder = ROOT / name
        monkeypatch.setenv("GEODATA_OFFLINE", "1")
        config.set_offline(True)
        monkeypatch.setattr(config, "demo_dir", lambda: folder / "geodata")
        monkeypatch.setattr(iung, "frozen_dir", lambda: folder / "soil")
        monkeypatch.setattr(background, "frozen_dir", lambda: folder / "satellite")
        monkeypatch.setattr(pages, "DEMO_DIR", folder / "smsr")
        monkeypatch.setattr(pages, "CACHE_DIR", folder / "no_cache")
        monkeypatch.setattr(pages, "ARCHIVE_DIR", folder / "no_archive")
        return BY_NAME[name]

    return switch


def _params(loc: dict, **extra: str) -> str:
    return urlencode({"dzialka": loc["parcel_id"], "data": loc["day"], "uprawa": loc["crop"], **extra})


_BUILT: dict[str, tuple[Report, float]] = {}
_SCREENS: dict[tuple[str, str], str] = {}


def _build(loc: dict) -> tuple[Report, float]:
    """The report and the seconds its first build took (later calls reuse it: the frozen data never change)."""
    if loc["name"] not in _BUILT:
        _BUILT[loc["name"]] = _build_once(loc)
    return _BUILT[loc["name"]]


def _build_once(loc: dict) -> tuple[Report, float]:
    started = time.perf_counter()
    r = TestClient(app).get(f"/api/raport?{_params(loc)}")
    took = time.perf_counter() - started
    assert r.status_code == 200, r.text[:300]
    return Report.model_validate(r.json()), took


@functools.cache
def _frozen_by_name(name: str):
    loc = BY_NAME[name]
    sample = load_sample(loc["parcel_id"], loc["day"], ROOT / name / "geodata")
    assert sample is not None
    return sample


def _frozen(loc: dict):
    return _frozen_by_name(loc["name"])


def _inside(x: float, y: float, ring: list[list[float]], tolerance_m: float = 1.0) -> bool:
    """Point in polygon by ray casting; a point within `tolerance_m` of an edge counts as inside."""
    inside = False
    n = len(ring)
    for i in range(n):
        (x1, y1), (x2, y2) = ring[i][:2], ring[(i + 1) % n][:2]
        dx, dy = x2 - x1, y2 - y1
        length2 = dx * dx + dy * dy
        t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / length2))
        if (x - x1 - t * dx) ** 2 + (y - y1 - t * dy) ** 2 <= tolerance_m**2:
            return True
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * dx / (y2 - y1):
            inside = not inside
    return inside


def _slope(loc: dict) -> float | None:
    terrain = _frozen(loc).terrain
    return terrain.data.slope_mean_pct if terrain.usable else None


def _nearest_ditch_m(loc: dict) -> float | None:
    water = _frozen(loc).water
    if not water.usable:
        return None
    distances = [f.distance_m for f in water.data.features if f.kind in ("ditch", "canal", "stream")]
    return min(distances) if distances else None


def _visible_text(page: str) -> str:
    page = re.sub(r"<(script|style)\b.*?</\1>", " ", page, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page)).lower()


def test_at_least_ten_locations_and_each_is_complete() -> None:
    assert 10 <= len(NAMES) <= 12
    assert len(set(NAMES)) == len(NAMES)
    for loc in LOCATIONS:
        folder = ROOT / loc["name"]
        assert (folder / "geodata").is_dir() and any((folder / "geodata").glob("*.json")), loc["name"]
        sample = _frozen(loc)
        assert sample.parcel.usable and sample.weather.usable and sample.terrain.usable, loc["name"]


def test_frozen_data_stay_small() -> None:
    size = sum(p.stat().st_size for p in ROOT.rglob("*") if p.is_file())
    assert size < 20 * 1024 * 1024, f"{size / 1e6:.1f} MB"


@pytest.mark.parametrize("name", NAMES)
def test_report_builds_from_frozen_data(name: str, use_location) -> None:
    loc = use_location(name)
    report, took = _build(loc)
    assert took < MAX_BUILD_S, f"{took:.1f} s"
    assert report.parcel.id == loc["parcel_id"]
    assert report.parcel.voivodeship.lower() == loc["voivodeship"]
    assert report.data_copy and report.data_copy.startswith("kopia danych z ")
    assert report.verdict.state != "no_data"
    assert report.sources


@pytest.mark.parametrize("name", NAMES)
def test_numbers_agree_with_each_other(name: str, use_location) -> None:
    report, _ = _build(use_location(name))
    for p in (report.verdict.period, *report.verdict.periods):
        if p is None:
            continue
        assert p.kbw_mm == pytest.approx(p.precip_mm - p.et0_mm, abs=0.11), p.n
        if p.threshold_mm is not None and p.margin_mm is not None:
            assert p.margin_mm == pytest.approx(p.kbw_mm - p.threshold_mm, abs=0.11), p.n
    top = report.verdict.period
    if top is not None and report.verdict.kbw_mm is not None:
        assert report.verdict.kbw_mm == pytest.approx(top.kbw_mm, abs=0.11)
        if report.verdict.state in ("below", "above"):
            assert report.verdict.threshold_mm == top.threshold_mm
            assert report.verdict.margin_mm == top.margin_mm
        # the sentence under the badge states the same balance in whole millimetres
        assert f"{abs(round(top.kbw_mm))}".replace("-", "") in report.verdict.how.replace("−", "").replace(
            " ", ""
        )


@pytest.mark.parametrize("name", NAMES)
def test_badge_follows_the_sign_of_the_margin(name: str, use_location) -> None:
    v = _build(use_location(name))[0].verdict
    if v.state in ("below", "above"):
        assert v.margin_mm is not None
        assert v.badge == (BADGE_BELOW if v.margin_mm < 0 else BADGE_ABOVE)
        assert v.state == ("below" if v.margin_mm < 0 else "above")
    else:
        assert v.badge not in (BADGE_BELOW, BADGE_ABOVE)


@pytest.mark.parametrize("name", NAMES)
def test_balance_window_matches_the_analysis_date(name: str, use_location) -> None:
    loc = use_location(name)
    day = date.fromisoformat(loc["day"])
    v = _build(loc)[0].verdict
    p = v.period
    if v.state == "out_of_season":
        assert v.season_year is not None and v.season_year <= day.year
        assert p is None or p.end <= day
        return
    assert p is not None, v.state
    assert p.start <= p.end
    assert p.start.year == day.year or v.state == "out_of_season"
    if p.complete:
        assert p.end <= day
        assert p.days == (p.end - p.start).days + 1
    else:
        assert p.start <= day <= p.end
        assert v.state == "running"
        elapsed = (day - p.start).days + 1
        assert 0 < p.days <= elapsed, (p.days, elapsed)
        assert elapsed - p.days <= MAX_DATA_LAG_DAYS, "the weather series ends too early for this date"


def _screen_text(loc: dict, screen: str) -> str:
    key = (loc["name"], screen)
    if key not in _SCREENS:
        path, extra = SCREENS[screen]
        r = TestClient(app).get(f"{path}?{_params(loc, **extra)}")
        assert r.status_code == 200
        _SCREENS[key] = _visible_text(r.text)
    return _SCREENS[key]


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("screen", sorted(SCREENS))
def test_no_screen_shows_a_forbidden_pattern(name: str, screen: str, use_location) -> None:
    """Every screen: no phrase about us or about applications; the farmer screen also no cause codes."""
    text = _screen_text(use_location(name), screen)
    for phrase in ("nasz", "wniosk", "dopłat"):
        assert phrase not in text, f"{screen}: «{phrase}»"
    assert "tu pojawi" not in text and "undefined" not in text and "none" not in text.split()


@pytest.mark.parametrize("name", NAMES)
def test_farmer_screen_has_no_team_words_and_no_cause_codes(name: str, use_location) -> None:
    text = _screen_text(use_location(name), "farmer")
    for phrase in ("zespołu", "widok doradcy", *CAUSE_CODES):
        assert phrase not in text, phrase


@pytest.mark.xfail(
    reason="the advisor tables and the print view still show «propozycja zespołu», cause codes and «widok doradcy»",
    strict=False,
)
@pytest.mark.parametrize("name", NAMES[:1])
@pytest.mark.parametrize("screen", ["print", "advisor"])
def test_advisor_material_has_no_team_words_and_no_cause_codes(name: str, screen: str, use_location) -> None:
    text = _screen_text(use_location(name), screen)
    for phrase in ("zespołu", "widok doradcy", *CAUSE_CODES):
        assert phrase not in text, f"{screen}: {phrase}"


@pytest.mark.parametrize("name", NAMES)
def test_retention_actions_have_a_place_inside_the_outline_or_a_reason(name: str, use_location) -> None:
    loc = use_location(name)
    report, _ = _build(loc)
    outline = _frozen(loc).parcel.data.rings_2180[0]
    for action in (a for a in report.actions if a.group == "retencja"):
        assert action.title and action.sentence and action.source and action.cause
        if action.place is None:
            assert action.no_place_reason.startswith("brak miejsca na działce, bo "), action.id
        else:
            assert _inside(action.place.x_2180, action.place.y_2180, outline), action.id
        c = action.candidate
        if c is None:
            continue
        assert c.action_id and c.confidence in ("niska", "średnia", "wysoka")
        if c.geometry is None:
            assert c.no_place_reason.startswith("brak miejsca na działce, bo "), action.id
        else:
            assert c.geometry.coordinates
            assert all(_inside(x, y, outline) for x, y in c.geometry.coordinates), action.id


def _candidates(loc: dict) -> list[PlaceCandidate]:
    f = _frozen(loc)
    terrain = f.terrain.data if f.terrain.usable else None
    water = f.water.data if f.water.usable else None
    return find_places(
        PlacementInput(
            outline_2180=f.parcel.data.rings_2180[0],
            grid=(terrain.catchment_grid or terrain.grid) if terrain else None,
            lowest_outline_point_2180=terrain.lowest_outline_point_2180 if terrain else None,
            water=water.features if water else [],
            slope_mean_pct=terrain.slope_mean_pct if terrain else None,
        )
    )


@pytest.mark.parametrize("name", NAMES)
def test_candidate_places_lie_in_the_outline_and_gaps_have_a_reason(name: str) -> None:
    loc = BY_NAME[name]
    outline = _frozen(loc).parcel.data.rings_2180[0]
    candidates = _candidates(loc)
    assert candidates
    for c in candidates:
        assert c.kind
        if c.place is None:
            assert c.reason, f"{c.kind}: no place and no reason"
            assert c.no_place_reason.startswith("brak miejsca na działce, bo ")
        else:
            assert c.place.lon and c.place.lat and c.place.kind
            # a weir, a ditch and a pond sit on the water feature, which may run along the boundary just outside
            tolerance = 10.0 if c.kind in ("zastawka", "rów", "zbiornik") else 1.0
            assert _inside(c.place.x_2180, c.place.y_2180, outline, tolerance), c.kind


@pytest.mark.parametrize("name", NAMES)
def test_grass_strip_needs_a_slope_and_says_so_when_it_has_none(name: str) -> None:
    strip = next(c for c in _candidates(BY_NAME[name]) if c.kind == "pas trawy")
    if strip.place is None:
        assert TOO_SMALL in strip.reason, strip.reason
        assert strip.length_m is None
    else:
        assert strip.slope_pct is not None and strip.slope_pct >= 0.5
        assert strip.length_m and strip.length_m > 0


def test_locations_cover_the_required_features() -> None:
    """The set is only useful when it differs: terrain, ditches, crops, voivodeships, season states."""
    strips = {
        loc["name"]: next(c for c in _candidates(loc) if c.kind == "pas trawy").place is not None
        for loc in LOCATIONS
    }
    assert any(strips.values()) and not all(strips.values()), (
        strips
    )  # a slope that allows a strip, and a flat one
    slopes = {loc["name"]: _slope(loc) for loc in LOCATIONS}
    ditches = {loc["name"]: _nearest_ditch_m(loc) for loc in LOCATIONS}
    known = [s for s in slopes.values() if s is not None]
    assert any(s < FLAT_SLOPE_PCT for s in known), slopes
    assert any(_frozen(loc).terrain.status == "fallback" for loc in LOCATIONS), (
        "a parcel outside the NMT coverage"
    )
    assert any(s >= SLOPED_PCT for s in known), slopes
    assert any(d is not None and d <= DITCH_NEAR_M for d in ditches.values()), ditches
    assert any(d is None or d > 500 for d in ditches.values()), ditches
    assert len({loc["crop"] for loc in LOCATIONS}) >= 4
    assert len({loc["voivodeship"] for loc in LOCATIONS}) >= 6
    months = [date.fromisoformat(loc["day"]) for loc in LOCATIONS]
    assert any(d.month in (10, 11, 12, 1, 2) for d in months), "a date outside the season"
    assert any(5 <= d.month <= 9 for d in months), "a date inside the season"
