"""A report for a parcel that is not in the committed copies: the waiting page, its fragments, explicit errors."""

from __future__ import annotations

import threading
import time
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient

from app import main
from app.models import SECTION_ORDER, Report

client = TestClient(main.app)

# Not a committed copy: the fake network answers ULDK with the recorded parcel whatever the id.
LIVE = {"dzialka": "146501_1.0001.1", "data": "2019-07-15", "uprawa": "zboza_jare"}


def q(params: dict = LIVE, **extra: str) -> str:
    return urlencode(params | extra)


def test_live_parcel_answers_with_the_full_report(net) -> None:
    r = client.get(f"/raport?{q()}")
    assert r.status_code == 200
    assert 'id="werdykt"' in r.text and "Tu pojawi" not in r.text
    assert 'hx-get="/raport/sekcja/' not in r.text  # a quick report is not a waiting page
    assert 'aria-busy="true"' not in r.text


def test_live_api_report_has_a_verdict_and_no_copy_label(net) -> None:
    r = client.get(f"/api/raport?{q()}")
    assert r.status_code == 200
    report = Report.model_validate(r.json())
    assert report.verdict.state is not None
    assert report.data_copy is None
    assert len(report.sections) == 8


def test_unknown_parcel_is_an_error_at_the_field_in_polish(net) -> None:
    r = client.get(f"/raport?{q(dzialka='999999_9.9999.1')}")
    assert 400 <= r.status_code < 500
    assert 'class="field-error" id="e-dzialka"' in r.text
    assert "ULDK nie zna działki 999999_9.9999.1" in r.text
    api = client.get(f"/api/raport?{q(dzialka='999999_9.9999.1')}")
    assert api.status_code == 422
    assert api.json()["bledy"][0]["field"] == "dzialka"


def test_no_weather_gives_no_verdict_no_actions_and_one_sentence_to_act_on(net) -> None:
    net.fail["archive-api"] = 429
    net.fail["power.larc"] = 500
    report = Report.model_validate(client.get(f"/api/raport?{q()}").json())
    assert report.verdict.state == "no_data"
    assert report.verdict.badge == "" and report.verdict.kbw_mm is None
    assert report.actions == [] and report.action_1 is None
    sentence = report.verdict.sentence
    assert sentence.count(".") == 1 and "spróbuj za minutę albo wybierz inną datę" in sentence
    page = client.get(f"/raport?{q()}")
    assert page.status_code == 200 and sentence in page.text


# ---- the waiting page ---------------------------------------------------------------------------------------


@pytest.fixture
def slow_report(net, monkeypatch):
    """The report needs 1.5 s while the page waits only 0.2 s, like a live report over 10 s."""
    monkeypatch.setattr(main, "FAST_WAIT_S", 0.2)
    main._jobs.clear()
    release = threading.Event()
    real = main.build_report

    def slow(req):
        release.wait(5)
        return real(req)

    monkeypatch.setattr(main, "build_report", slow)
    yield release
    release.set()
    main._jobs.clear()


def test_slow_live_report_shows_photo_and_verdict_first(slow_report) -> None:
    page = client.get(f"/raport?{q()}")
    assert page.status_code == 200
    text = page.text
    assert 'aria-busy="true"' in text
    assert "/raport/zdjecie?" in text and 'class="mo-outline"' in text
    assert "Brak: bilansu wody" not in text and 'id="zdanie-werdyktu"' in text
    for sid, _, _ in SECTION_ORDER:
        assert f'hx-get="/raport/sekcja/{sid}?' in text
    assert text.count("Liczę… czekam na:") >= 9
    assert "Tu pojawi" not in text
    assert 'hx-get="/raport/wynik?' in text
    slow_report.set()


def test_sections_and_result_arrive_when_the_report_is_ready(slow_report) -> None:
    client.get(f"/raport?{q()}")
    slow_report.set()
    for sid, n, _ in SECTION_ORDER:
        frag = client.get(f"/raport/sekcja/{sid}?{q()}")
        assert frag.status_code == 200 and f'<section id="{sid}"' in frag.text
        assert f'<span class="n">{n}</span>' in frag.text
        assert "delay:2000ms" not in frag.text
    result = client.get(f"/raport/wynik?{q()}")
    assert result.status_code == 200
    for marker in (
        'id="naglowek" hx-swap-oob',
        'id="werdykt" hx-swap-oob',
        'id="skrot" hx-swap-oob',
        'id="mapa" hx-swap-oob',
    ):
        assert marker in result.text, marker
    assert "Ocena SMSR dla gminy" in result.text


def test_a_section_asks_again_while_the_report_is_computing(slow_report, monkeypatch) -> None:
    monkeypatch.setattr(main, "SECTION_WAIT_S", 0.1)
    frag = client.get(f"/raport/sekcja/przyczyny?{q()}")
    assert frag.status_code == 200
    assert 'hx-trigger="load delay:2000ms"' in frag.text and "Liczę… czekam na" in frag.text
    slow_report.set()
    time.sleep(0.5)
    done = client.get(f"/raport/sekcja/przyczyny?{q()}")
    assert "delay:2000ms" not in done.text


def test_a_failed_report_ends_the_waiting_page_with_a_sentence(net, monkeypatch) -> None:
    monkeypatch.setattr(main, "FAST_WAIT_S", 0.0)
    page = client.get(f"/raport?{q(dzialka='999999_9.9999.1')}")
    assert page.status_code == 422 and "e-dzialka" in page.text
    frag = client.get(f"/raport/sekcja/gmina?{q(dzialka='999999_9.9999.1')}")
    assert frag.status_code == 200 and "ULDK nie zna działki" in frag.text and "<script" not in frag.text


def test_unknown_section_is_404(net) -> None:
    assert client.get(f"/raport/sekcja/nie-ma?{q()}").status_code == 404


def test_a_crash_is_a_sentence_not_a_trace(net, monkeypatch) -> None:
    def broken(req):
        raise RuntimeError("boom")

    monkeypatch.setattr(main, "build_report", broken)
    r = client.get(f"/raport?{q()}")
    assert r.status_code == 500 and "Spróbuj za chwilę" in r.text and "boom" not in r.text
    api = client.get(f"/api/raport?{q()}")
    assert api.status_code == 500 and api.json()["bledy"][0]["field"] == "dzialka"


@pytest.mark.live
def test_ten_voivodeships_live_in_30_s() -> None:
    import os

    if os.environ.get("GEODATA_LIVE") != "1":
        pytest.skip("live test: set GEODATA_LIVE=1")
    from app.geodata import http

    http.set_client(None)
    ids = [  # one real farmland parcel in each of 10 voivodeships (found with ULDK GetParcelByXY on 21.11.2026)
        "302504_5.0028.14/4", "062006_2.0005.74", "161002_5.0021.AR_7.337/39", "021701_2.0021.254/363",
        "142003_2.0033.37/2", "200208_2.0003.2/4", "280103_2.0059.352", "121406_2.0015.127",
        "220903_2.0005.125/5", "040303_2.0002.189/13",
    ]  # fmt: skip
    for pid in ids:
        started = time.monotonic()
        r = client.get(f"/api/raport?{q(dzialka=pid, data='2019-07-15')}")
        took = time.monotonic() - started
        assert r.status_code == 200, (pid, r.text[:300])
        report = Report.model_validate(r.json())
        assert took <= 30, (pid, took)
        assert report.verdict.state is not None
        assert report.data_copy in (None, "") or pid == "040303_2.0002.189/13"
        page = client.get(f"/raport?{q(dzialka=pid, data='2019-07-15')}")
        assert "Tu pojawi" not in page.text
