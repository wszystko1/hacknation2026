"""SMSR row of the commune: parser, row for the demo parcels, pages from disk and network, the gaps."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.geodata import http
from app.models import CropGroup
from app.smsr import pages
from app.smsr.parser import SmsrPageError, parse_commune_page
from tests.acceptance.helpers import DOBRCZ, GSM_TODAY, html, report

FIXTURE = Path(__file__).parent / "fixtures" / "smsr" / "2023_0403043.html"
DEMO_PAGE = Path(__file__).resolve().parents[1] / "demo" / "data" / "smsr" / "2023_0403032.html"


@pytest.fixture
def table():
    return parse_commune_page(FIXTURE.read_text(encoding="utf-8"))


def test_parser_reads_14_crops_14_periods_4_categories_and_the_shares(table) -> None:
    assert (table.commune, table.teryt, table.year) == ("Koronowo", "0403043", 2023)
    assert len(table.cells) == 14 * 14 * 4
    assert len(table.shares) == 14 * 14
    assert len(table.crops()) == 14
    assert table.periods[7] == ("2023-05-21", "2023-07-20")


def test_parser_symbols_and_shares_match_the_page(table) -> None:
    assert table.symbol("Zboża jare", "I", 7) == "+"
    assert table.area_share_pct("Zboża jare", 7) == 97.33
    assert table.symbol("Kukurydza na ziarno", "I", 1) == "x"
    assert table.area_share_pct("Kukurydza na ziarno", 1) is None  # "x": no share
    assert table.symbol("Zboża jare", "I", 9) == "-"
    assert table.area_share_pct("Zboża jare", 9) == 0.0
    assert table.symbol("Zboża jare", "V", 7) is None
    assert table.symbol("Nieznana uprawa", "I", 7) is None


def test_parser_symbols_stay_in_the_legend(table) -> None:
    assert set(table.cells.values()) <= {"+", "-", "x", "#", "*", "n"}


def test_parser_joins_fruit_rows_that_some_years_publish_as_one() -> None:
    text = FIXTURE.read_text(encoding="utf-8")
    one_row = text.replace("Drzewa owocowe", "Drzewa i krzewy owocowe")
    one_row = one_row.replace("Krzewy owocowe", "Drzewa i krzewy owocowe")
    t = parse_commune_page(one_row)
    assert t.symbol("Krzewy owocowe", "II", 5) == t.symbol("Drzewa owocowe", "II", 5) is not None


@pytest.mark.parametrize("text", ["", "<html><body>Przerwa techniczna</body></html>"])
def test_parser_refuses_a_page_that_is_not_a_commune_table(text: str) -> None:
    with pytest.raises(SmsrPageError):
        parse_commune_page(text)


def test_row_for_dobrcz_comes_from_the_frozen_page_without_network(net) -> None:
    net.down = True
    r = report(DOBRCZ)
    frozen = parse_commune_page(DEMO_PAGE.read_text(encoding="utf-8"))
    assert r.smsr.state == "ok"
    assert (r.smsr.commune, r.smsr.year, r.smsr.period_n) == ("Dobrcz", 2023, r.verdict.period.n)
    assert r.smsr.crop_label == "Zboża jare"
    assert r.smsr.soil_category == r.soil.category
    assert r.smsr.symbol == frozen.symbol("Zboża jare", r.soil.category, r.verdict.period.n)
    assert r.smsr.area_share_pct == frozen.area_share_pct("Zboża jare", r.verdict.period.n)
    assert r.smsr.words and r.smsr.url.endswith("/wykazy/2023,0403032/")
    assert net.count("susza.iung") == 0


def test_row_for_gora_swietej_malgorzaty_is_the_last_season_of_2026() -> None:
    r = report(GSM_TODAY)
    assert r.smsr.state == "ok"
    assert r.smsr.commune == "Góra Świętej Małgorzaty"
    assert r.smsr.year == 2026
    assert r.smsr.period_n == r.verdict.period.n
    assert r.smsr.crop_label == "Rośliny strączkowe"


def test_source_row_has_the_time_and_marks_the_frozen_copy() -> None:
    row = next(s for s in report(DOBRCZ).sources if s.key == "smsr")
    assert row.status == "copy"
    assert row.retrieved_at.startswith("2026-11-21")
    assert row.elapsed_s is not None and row.elapsed_s > 0
    assert row.url.startswith("https://susza.iung.pulawy.pl/wykazy/2023,")
    assert row.gave.startswith("gmina Dobrcz")


def test_date_before_2020_says_so_in_polish() -> None:
    r = report({**DOBRCZ, "data": "2019-07-20"})
    assert r.smsr.state == "before_2020"
    assert r.smsr.reason.startswith("Brak:") and " bo " in r.smsr.reason and "2020" in r.smsr.reason
    row = next(s for s in r.sources if s.key == "smsr")
    assert row.status == "missing" and row.reason == r.smsr.reason and row.url == ""


def test_other_crop_has_no_row_and_says_why() -> None:
    r = report({**DOBRCZ, "uprawa": CropGroup.INNA.value})
    assert r.smsr.state == "missing"
    assert r.smsr.reason.startswith("Brak: ocena SMSR dla gminy Dobrcz, bo ")


def test_unknown_soil_category_has_no_row_and_says_why(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import report as report_module
    from app.models import SoilInfo

    monkeypatch.setattr(
        report_module, "assess_soil", lambda ctx: SoilInfo(category=None, source="brak", words="brak")
    )
    r = report(DOBRCZ)
    assert r.smsr.state == "missing"
    assert "kategorii gleby" in r.smsr.reason and " bo " in r.smsr.reason


@pytest.mark.parametrize("params", [DOBRCZ, GSM_TODAY], ids=["dobrcz", "gora-swietej-malgorzaty"])
@pytest.mark.parametrize("path", ["/raport", "/raport/druk"])
def test_report_routes_show_the_row_not_a_placeholder(path: str, params: dict) -> None:
    page = html(params, path=path)
    r = report(params)
    assert "Tu pojawi" not in page
    assert f"Ocena SMSR dla gminy {r.smsr.commune} w tym okresie" in page
    assert r.smsr.words in page


# ---------------------------------------------------------------- pages: disk cache and network


@pytest.fixture
def empty_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(pages, "DEMO_DIR", tmp_path / "demo")
    monkeypatch.setattr(pages, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(pages, "ARCHIVE_DIR", tmp_path / "archive")
    return tmp_path


def serve(status: int = 200) -> list[str]:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(status, text=FIXTURE.read_text(encoding="utf-8") if status == 200 else "x")

    http.set_client(httpx.Client(transport=httpx.MockTransport(handler)))
    return calls


def test_live_page_is_saved_and_the_second_request_reads_the_disk(empty_dirs: Path) -> None:
    calls = serve()
    first = pages.load_page(2023, "0403043")
    second = pages.load_page(2023, "0403043")
    assert (first.origin, second.origin) == ("live", "cache")
    assert calls == ["https://susza.iung.pulawy.pl/wykazy/2023,0403043/"]
    assert second.retrieved_at == first.retrieved_at
    meta = json.loads((empty_dirs / "cache" / "2023_0403043.json").read_text(encoding="utf-8"))
    assert meta["retrieved_at"] == first.retrieved_at


def test_downloaded_archive_is_read_before_the_network(empty_dirs: Path) -> None:
    calls = serve()
    (empty_dirs / "archive").mkdir()
    (empty_dirs / "archive" / "2022_0403043.html").write_text(FIXTURE.read_text(encoding="utf-8"))
    assert pages.load_page(2022, "0403043").origin == "archive"
    assert calls == []


def test_page_of_the_current_year_is_not_kept_for_good(empty_dirs: Path) -> None:
    from datetime import UTC, datetime

    calls = serve()
    now = datetime(2026, 11, 21, 12, tzinfo=UTC)
    pages.load_page(2026, "0403043", today=now)
    same_day = pages.load_page(2026, "0403043", today=now.replace(hour=20))
    next_day = pages.load_page(2026, "0403043", today=now.replace(day=22))
    assert (same_day.origin, next_day.origin) == ("cache", "live")
    assert len(calls) == 2


def test_missing_page_and_dead_service_give_different_reasons(empty_dirs: Path) -> None:
    serve(404)
    with pytest.raises(pages.PageUnavailable, match="nie opublikował"):
        pages.load_page(2023, "9999999")
    serve(503)
    with pytest.raises(pages.PageUnavailable, match="nie odpowiedział"):
        pages.load_page(2023, "9999999")


def test_row_without_a_page_is_one_sentence_with_a_reason(empty_dirs: Path, net) -> None:
    net.down = True
    r = report(DOBRCZ)
    assert r.smsr.state == "missing"
    assert r.smsr.reason == "Brak: ocena SMSR dla gminy Dobrcz, bo wykaz IUNG nie odpowiedział"
    row = next(s for s in r.sources if s.key == "smsr")
    assert row.status == "missing" and row.reason == r.smsr.reason
    assert "Brak: ocena SMSR dla gminy Dobrcz, bo wykaz IUNG nie odpowiedział" in html(DOBRCZ)
