"""The sources table: every row says in Polish what it gave, the rows are the sources the report uses,
the Sentinel-2 row carries the scene date or says the plant assessment is still running, and the
adviser block of the plan names the forecast method and its measured skill."""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from app.models import CropCondition, ExceedanceForecast
from app.sections.zrodla import plan_advisor
from app.sources_table import sentinel_gave
from tests.acceptance.helpers import DOBRCZ, GSM_TODAY, html, report

ENGLISH = re.compile(
    r"\b(the|from|grid|station|service|orthophoto|resolution|daily|cadastral|requested|clouds|revisit|global|"
    r"image|pixel|sampled|rendered|database|measurements)\b",
    re.IGNORECASE,
)
PARCELS = [DOBRCZ, GSM_TODAY]
IDS = ["dobrcz", "gora"]


@pytest.mark.parametrize("params", PARCELS, ids=IDS)
def test_every_row_has_a_polish_label_and_what_it_gave(params: dict) -> None:
    rows = report(params).sources
    assert len(rows) >= 9
    for r in rows:
        assert r.label and r.provider
        for text in (r.label, r.gave, r.resolution, r.reason):
            assert not ENGLISH.search(text), (r.key, text)
        if r.status in ("ok", "copy", "fallback"):
            assert r.gave, f"{r.key}: nothing said about what the source gave"


def test_weather_row_names_the_years_the_station_and_its_distance() -> None:
    gave = next(r for r in report(DOBRCZ).sources if r.key == "weather").gave
    assert re.search(r"opad 2013–2023 \(posterunek NOWY JASINIEC, 11 km\)", gave)
    assert "parowanie" in gave


def _context_with_crop_map(status: str):
    import dataclasses
    from datetime import date

    from app import datasource
    from app.geodata.models import CropClass, CropHint, SourceResult
    from app.models import CropGroup, ReportRequest
    from app.report import build_context

    req = ReportRequest(parcel_id=DOBRCZ["dzialka"], day=date(2023, 7, 20), crop=CropGroup.ZBOZA_JARE)
    ctx = build_context(req)
    hint = CropHint(
        map_year=2022,
        classes=[CropClass(code=1, name="zboża jare", share=0.82)],
        dominant="zboża jare",
        pixels=900,
    )
    source = SourceResult(
        source="crop_hint", status=status, data=hint if status == "ok" else None, elapsed_ms=1200, error="x"
    )
    ctx.data = dataclasses.replace(ctx.data, crop_hint=source)
    assert datasource  # the copy of the demo parcel is what build_context loaded
    return ctx


def test_table_lists_forecast_and_crop_map_but_not_the_seasonal_forecast() -> None:
    from app.sources_table import source_rows

    rows = source_rows(_context_with_crop_map("ok"))
    labels = [r.label for r in rows]
    assert "Prognoza 16 dni" in labels
    crop = next(r for r in rows if r.label == "Mapa upraw JRC 2022")
    assert crop.gave == "mapa za rok 2022: zboża jare, 82% obrysu" and crop.status == "copy"
    assert not any("sezon" in label.lower() for label in labels)
    page = html(DOBRCZ)
    assert "Prognoza 16 dni" in page and "sezonowa" not in page.lower()


def test_a_failed_crop_map_is_a_gap_with_a_reason_and_an_unrequested_one_has_no_row() -> None:
    from app.sources_table import source_rows

    failed = next(r for r in source_rows(_context_with_crop_map("error")) if r.key == "crop_hint")
    assert failed.status == "missing" and failed.reason == "usługa nie odpowiedziała"
    assert "Mapa upraw JRC 2022" not in [r.label for r in report(DOBRCZ).sources]


def test_copy_rows_carry_the_date_of_the_copy() -> None:
    page = html(DOBRCZ, widok="doradca")
    assert "kopia z dnia 21.11.2026" in page


def test_the_report_names_what_it_does_not_cover_and_where_the_soil_category_comes_from() -> None:
    text = " ".join(report(DOBRCZ).section("zrodla").sentences)
    assert "drenowania, wód gruntowych ani faktycznej daty siewu" in text
    assert "mapa podatności gleb na suszę IUNG-PIB" in text
    assert "11 km od działki" in text


def test_resolution_is_only_in_the_adviser_block() -> None:
    page = html(DOBRCZ, widok="doradca")
    table = re.search(r'<table id="tabela-zrodel">.*?</table>', page, re.S)
    assert table and "Rozdzielczość" not in table.group(0) and "piksel źródłowy" not in table.group(0)
    assert "rozdzielczość źródeł" in page and "piksel źródłowy do 0,25 m" in page


def test_sentinel_row_has_the_scene_date_for_dobrcz() -> None:
    row = next(r for r in report(DOBRCZ).sources if r.key == "satellite")
    assert re.search(r"\d{2}\.\d{2}\.\d{4}", row.gave) or "ocena roślin w toku" in row.gave
    assert "czystych pikseli 19%" in row.gave and "porównywalnych sezonów" in row.gave


def test_sentinel_row_says_the_assessment_is_running_while_it_waits() -> None:
    ctx = SimpleNamespace(
        crop_condition=CropCondition(state="waiting", words="ocena roślin w toku"),
        data=SimpleNamespace(satellite=SimpleNamespace(usable=True, data=None)),
    )
    assert sentinel_gave(ctx) == ("ocena roślin w toku", "")  # type: ignore[arg-type]


def test_sentinel_row_without_a_scene_is_a_gap_with_a_reason() -> None:
    ctx = SimpleNamespace(
        crop_condition=CropCondition(state="missing", words="Brak: stanu roślin"),
        data=SimpleNamespace(satellite=SimpleNamespace(usable=True, data=SimpleNamespace(current=None))),
    )
    gave, reason = sentinel_gave(ctx)  # type: ignore[arg-type]
    assert gave == "" and "zdjęcia" in reason


def _plan_ctx(metrics: dict) -> SimpleNamespace:
    forecast = ExceedanceForecast(state="ok", method="analog", k=4, n=10, years_used=list(range(2013, 2023)))
    return SimpleNamespace(forecast=forecast, metrics=metrics)


def test_plan_advisor_names_the_method_and_the_skill_from_metrics() -> None:
    metrics = {
        "forecast.brier_skill": 0.071,
        "forecast.brier_skill_ci_low": 0.02,
        "forecast.brier_skill_ci_high": 0.12,
        "forecast.brier": 0.181,
        "forecast.calibration": [{"observed_pct": 10 * i, "n": 20} for i in range(10)],
    }
    rows = {kv.key: kv.value for kv in plan_advisor(_plan_ctx(metrics))}  # type: ignore[arg-type]
    assert "dopełnianie przebiegami" in rows["Metoda prognozy"]
    assert rows["Lata w prognozie"] == "10 (2013–2022)"
    assert rows["Częstość historyczna"] == "4 z 10 wcześniejszych lat"
    assert rows["BSS"].startswith("0,071, przedział 95%: 0,020 do 0,120")
    assert rows["Brier"].startswith("0,181")
    assert rows["Kalibracja (10 przedziałów)"].count("n=20") == 10


def test_plan_advisor_explains_brier_and_bss_in_one_sentence_each() -> None:
    rows = {kv.key: kv.value for kv in plan_advisor(_plan_ctx({}))}  # type: ignore[arg-type]
    for key in ("Brier", "BSS"):
        explanation = rows[key].split(". ", 1)[1]
        assert len(explanation) >= 15, key
    assert rows["BSS"].startswith("brak: pomiaru") and "Kalibracja" in " ".join(rows)


def test_the_farmer_view_has_no_bss_or_brier_outside_advisor_blocks() -> None:
    page = html(DOBRCZ)
    page = re.sub(r'<div class="advisor".*?</div>', " ", page, flags=re.S)
    page = re.sub(r"<(script|style)\b.*?</\1>", " ", page, flags=re.S)
    assert "BSS" not in page and "Brier" not in page
