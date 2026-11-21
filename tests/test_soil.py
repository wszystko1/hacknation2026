"""Soil category: texture rule, IUNG map reading, and what the report routes show for both demo parcels."""

from __future__ import annotations

import dataclasses

import httpx
import pytest
from fastapi.testclient import TestClient

from app.geodata import http
from app.main import app
from app.models import BADGE_ABOVE, BADGE_BELOW, ReportRequest
from app.report import build_context
from app.soil import assess_soil, iung
from app.soil.texture import CATEGORY_OF_CLASS, category_from_texture

client = TestClient(app)

DOBRCZ = "dzialka=040303_2.0002.189/13&data=2023-07-20&uprawa=zboza_jare"
GSM = "dzialka=100403_2.0011.144&data=2026-11-21&uprawa=rosliny_straczkowe"
STUB = "Tu pojawi się kategoria gleby"


def _context(soil_override: str | None = None):
    from datetime import date

    return build_context(
        ReportRequest.model_validate(
            {
                "parcel_id": "040303_2.0002.189/13",
                "day": date(2023, 7, 20),
                "crop": "zboza_jare",
                "soil_override": soil_override,
            }
        )
    )


# ---------------------------------------------------------------- texture rule


@pytest.mark.parametrize(
    ("fractions", "category"),
    [
        ((95.0, 4.0, 1.0), "I"),  # sand
        ((85.0, 10.0, 5.0), "I"),  # loamy sand
        ((68.0, 22.0, 10.0), "II"),  # sandy loam
        ((40.0, 40.0, 20.0), "III"),  # loam
        ((15.0, 70.0, 15.0), "III"),  # silt loam
        ((30.0, 35.0, 35.0), "IV"),  # clay loam
        ((10.0, 40.0, 50.0), "IV"),  # silty clay
    ],
)
def test_texture_gives_the_category_of_its_class(
    fractions: tuple[float, float, float], category: str
) -> None:
    assert category_from_texture(*fractions)[0] == category


def test_every_usda_class_maps_to_a_category() -> None:
    from app.geodata.soil import usda_texture_class

    seen = {
        usda_texture_class(s, 100.0 - s - c, c)
        for s in range(0, 101, 2)
        for c in range(0, 101, 2)
        if s + c <= 100
    }
    assert seen <= set(CATEGORY_OF_CLASS)


def test_neighbour_is_adjacent_and_on_the_side_of_the_boundary() -> None:
    category, neighbour = category_from_texture(sand_pct=82.0, silt_pct=8.0, clay_pct=10.0)
    assert category == "I"
    assert neighbour == "II"
    category, neighbour = category_from_texture(sand_pct=78.0, silt_pct=12.0, clay_pct=10.0)
    assert category == "II"
    assert neighbour == "I"


def test_texture_far_from_a_boundary_has_no_neighbour() -> None:
    assert category_from_texture(sand_pct=97.0, silt_pct=2.0, clay_pct=1.0) == ("I", None)


# ---------------------------------------------------------------- IUNG layer


def test_classify_takes_the_most_frequent_category() -> None:
    reading = iung.IungReading("x", {"2": 6, "3": 3}, points=9)
    result = iung.classify(reading)
    assert (result.category, result.other, result.in_points, result.of_points) == ("II", "III", 6, 9)


def test_classify_ignores_masked_land_cover_and_tie_goes_to_the_lighter_soil() -> None:
    result = iung.classify(iung.IungReading("x", {"11": 5, "3": 2, "2": 2}, points=9))
    assert (result.category, result.of_points) == ("II", 4)


def test_classify_reports_organic_soil_without_a_category() -> None:
    result = iung.classify(iung.IungReading("x", {"5": 4, "11": 1}, points=5))
    assert result.category is None
    assert result.organic


def test_sample_points_lie_inside_the_outline_and_not_in_holes() -> None:
    outline = [[0.0, 0.0], [0.01, 0.0], [0.01, 0.01], [0.0, 0.01], [0.0, 0.0]]
    hole = [[0.004, 0.004], [0.006, 0.004], [0.006, 0.006], [0.004, 0.006], [0.004, 0.004]]
    points = iung.sample_points([outline, hole])
    assert 1 <= len(points) <= iung.MAX_POINTS
    for lon, lat in points:
        assert 0.0 < lon < 0.01
        assert 0.0 < lat < 0.01
        assert not (0.004 < lon < 0.006 and 0.004 < lat < 0.006)


def _iung_service(values: list[int] | None, seen: list[httpx.Request] | None = None):
    """A fake GeoServer answering GetFeatureInfo with the given cell values in turn; None = HTTP 503."""
    queue = list(values or [])

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        if values is None:
            return httpx.Response(503, text="down")
        value = queue.pop(0) if queue else queue_default
        return httpx.Response(200, json={"features": [{"properties": {"GRAY_INDEX": value}}]})

    queue_default = (values or [0])[-1]
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_live_reading_asks_the_layer_with_latitude_first_and_counts_values() -> None:
    seen: list[httpx.Request] = []
    http.set_client(_iung_service([3], seen))
    ring = [[18.10, 53.20], [18.12, 53.20], [18.12, 53.22], [18.10, 53.22], [18.10, 53.20]]
    reading = iung.read_live("x", [ring])
    assert reading is not None
    assert reading.counts == {"3": reading.points}
    params = seen[0].url.params
    assert params["layers"] == params["query_layers"] == iung.LAYER
    assert params["bbox"].startswith("53.")  # EPSG:4326 in WMS 1.3.0: latitude first


def test_live_reading_is_none_when_the_service_is_down() -> None:
    http.set_client(_iung_service(None))
    ring = [[18.10, 53.20], [18.12, 53.20], [18.12, 53.22], [18.10, 53.22], [18.10, 53.20]]
    assert iung.read_live("x", [ring]) is None


def test_frozen_readings_exist_for_both_demo_parcels() -> None:
    for parcel in ("040303_2.0002.189/13", "100403_2.0011.144"):
        reading = iung.load_frozen(parcel)
        assert reading is not None
        assert iung.classify(reading).category in {"I", "II", "III", "IV"}


# ---------------------------------------------------------------- assess_soil


def test_category_comes_from_the_frozen_map_reading() -> None:
    ctx = _context()
    soil = assess_soil(ctx)
    assert (soil.category, soil.source) == ("II", "iung")
    assert soil.words == "gleba podatna na suszę (kat. II)"
    row = next(r for r in ctx.extra_sources if r.key == "soil_category")
    assert row.label == "Kategoria gleby"
    assert row.status == "copy"
    assert "kat. II" in row.gave


def test_offline_the_category_of_both_demo_parcels_comes_from_demo_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEODATA_OFFLINE", "1")
    for query in (DOBRCZ, GSM):
        body = client.get(f"/api/raport?{query}").json()
        assert body["soil"]["category"] == "II"
        assert body["soil"]["source"] == "iung"


def test_advisor_setting_wins_over_the_map() -> None:
    ctx = _context(soil_override="IV")
    soil = assess_soil(ctx)
    assert (soil.category, soil.source) == ("IV", "doradca")
    assert any(r.provider == "doradca" for r in ctx.extra_sources)


def test_without_the_map_soilgrids_texture_gives_the_category_and_the_neighbour(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(iung, "read_for_parcel", lambda parcel_id, rings: (None, False))
    ctx = _context()
    soil_result = dataclasses.replace(
        ctx.data.soil,
        data=dataclasses.replace(ctx.data.soil.data, sand_pct=82.0, silt_pct=8.0, clay_pct=10.0),
    )
    ctx.data = dataclasses.replace(ctx.data, soil=soil_result)
    soil = assess_soil(ctx)
    assert (soil.category, soil.source, soil.neighbour_category) == ("I", "soilgrids", "II")
    assert "blisko granicy z kat. II" in soil.words
    row = next(r for r in ctx.extra_sources if r.key == "soil_category")
    assert row.status == "fallback"
    assert row.reason


def test_without_any_source_the_answer_is_one_sentence_brak_bo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(iung, "read_for_parcel", lambda parcel_id, rings: (None, False))
    ctx = _context()
    ctx.data = dataclasses.replace(
        ctx.data, soil=dataclasses.replace(ctx.data.soil, status="error", data=None)
    )
    soil = assess_soil(ctx)
    assert soil.category is None
    assert soil.source == "brak"
    assert soil.words.startswith("Brak: ")
    assert ", bo " in soil.words
    assert soil.words.count(".") == 0
    row = next(r for r in ctx.extra_sources if r.key == "soil_category")
    assert (row.status, bool(row.reason)) == ("missing", True)


def test_a_broken_map_service_falls_back_to_soilgrids(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(parcel_id: str, rings: list) -> tuple:
        raise RuntimeError("boom")

    monkeypatch.setattr(iung, "read_for_parcel", broken)
    soil = assess_soil(_context())
    assert soil.source == "soilgrids"
    assert soil.category is not None


# ---------------------------------------------------------------- the routes the UI calls


def test_api_report_has_the_category_the_threshold_and_the_badge_that_the_page_shows() -> None:
    body = client.get(f"/api/raport?{DOBRCZ}").json()
    assert body["soil"]["category"] in {"I", "II", "III", "IV"}
    assert body["verdict"]["threshold_mm"] is not None
    assert body["verdict"]["badge"] in {BADGE_BELOW, BADGE_ABOVE}
    page = client.get(f"/raport?{DOBRCZ}")
    assert page.status_code == 200
    assert body["verdict"]["badge"] in page.text.replace("&#39;", "'")


@pytest.mark.parametrize("query", [DOBRCZ, GSM])
@pytest.mark.parametrize("path_suffix", ["", "&widok=doradca"])
def test_pages_name_the_soil_and_never_show_the_placeholder(query: str, path_suffix: str) -> None:
    for path in ("/raport", "/raport/druk"):
        text = client.get(f"{path}?{query}{path_suffix}").text
        assert STUB not in text
        assert "kat. II" in text


def test_sources_table_has_the_category_row() -> None:
    text = client.get(f"/raport/sekcja/zrodla?{DOBRCZ}").text
    assert "Kategoria gleby" in text
    assert "IUNG" in text
