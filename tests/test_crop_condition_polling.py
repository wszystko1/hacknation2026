"""The plants block: a picture that is still being fetched is said so and polled for; a failure says why."""

from __future__ import annotations

import dataclasses
import threading
from datetime import date

import pytest

from app import main
from app.crop_condition import background
from app.geodata.parcel import parse_uldk
from app.models import CropCondition
from tests.acceptance.helpers import DOBRCZ, client, html, query
from tests.conftest import fixture_text

NO_COPY = DOBRCZ | {"dzialka": "141201_1.0001.77"}  # a parcel without a frozen copy of the seasons
READ = CropCondition(
    state="ok",
    words="rośliny słabsze niż w 4 porównywalnych latach",
    scene_date=date(2023, 7, 18),
    n_seasons=4,
)
WAITING = CropCondition(state="waiting", words="ocena roślin w toku")
NOT_COUNTED_PLANTS = "Nie ujęto w raporcie: stan roślin"
FAILED_SENTENCE = (
    "Nie udało się pobrać zdjęcia satelitarnego (przyczyna: {}). Ocena stanu roślin nie jest ujęta."
)


@pytest.fixture
def parcel():
    return dataclasses.replace(parse_uldk(fixture_text("uldk_ok.txt")), id="141201_1.0001.77")


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch, parcel):
    monkeypatch.setattr(background, "_running", {})
    monkeypatch.setattr(background, "_failed", {})
    monkeypatch.setattr(background, "_attempts", {})
    monkeypatch.setattr(main, "_parcel_of", lambda req: parcel)


def _frozen():
    return background.load_frozen(DOBRCZ["dzialka"], main_day())


def _seasons_calls(monkeypatch, answers: list[tuple]) -> list[int]:
    """seasons_for answers in this order, then keeps repeating the last one."""
    calls: list[int] = []

    def seasons_for(parcel, day):
        calls.append(1)
        return answers[min(len(calls), len(answers)) - 1]

    monkeypatch.setattr(background, "seasons_for", seasons_for)
    return calls


def _poll(proba: int, place: str = "wiersz", **extra: str):
    return client.get(f"/raport/stan-roslin?{query(DOBRCZ, miejsce=place, proba=str(proba), **extra)}")


def _polls(text: str) -> bool:
    return "hx-get=" in text and "hx-trigger=" in text


def test_waiting_report_says_the_picture_is_fetched_and_does_not_list_plants_as_missing(monkeypatch) -> None:
    monkeypatch.setattr("app.report.assess_crop_condition", lambda ctx: WAITING)
    page = html()
    assert "Pobieranie zdjęcia satelitarnego…" in page
    assert NOT_COUNTED_PLANTS not in page
    assert 'hx-get="/raport/stan-roslin?' in page and 'hx-trigger="load delay:4s"' in page
    assert 'id="stan-roslin-wiersz"' in page and 'id="stan-roslin-brak"' in page
    assert "Stan roślin ze zdjęcia satelitarnego: pobieranie zdjęcia" in page  # the Wiarygodność tab


def test_waiting_adviser_view_polls_in_the_verdict_facts(monkeypatch) -> None:
    monkeypatch.setattr("app.report.assess_crop_condition", lambda ctx: WAITING)
    page = html(widok="doradca")
    row = page.split('id="wiersz-satelita"')[1].split("</dl>")[0]
    assert "Pobieranie zdjęcia satelitarnego…" in row and 'id="stan-roslin-werdykt"' in row
    assert "ocena roślin w toku" not in row


def test_poll_waits_twice_then_returns_the_section_and_the_polling_ends(monkeypatch) -> None:
    monkeypatch.setattr("app.report.assess_crop_condition", lambda ctx: READ)
    _seasons_calls(monkeypatch, [("waiting", {}, ""), ("waiting", {}, ""), ("ready", _frozen(), "")])
    first, second, third = _poll(1), _poll(2), _poll(3)
    assert "Pobieranie zdjęcia satelitarnego…" in first.text and "proba=2" in first.text
    assert "Pobieranie zdjęcia satelitarnego…" in second.text and "proba=3" in second.text
    assert 'hx-trigger="load delay:5s"' in second.text
    assert 'id="stan-roslin-wiersz"' in third.text and not _polls(third.text)
    assert (
        "rośliny słabsze niż w 4 porównywalnych latach" in third.text
        and "Zdjęcie satelitarne z 18 lipca" in third.text
    )  # the sentences of the finished row


def test_ready_block_of_the_verdict_facts_and_the_line_of_gaps(monkeypatch) -> None:
    monkeypatch.setattr("app.report.assess_crop_condition", lambda ctx: READ)
    _seasons_calls(monkeypatch, [("ready", _frozen(), "")])
    facts = _poll(1, "werdykt").text
    assert 'id="stan-roslin-werdykt"' in facts and "(zdjęcie z 18.07.2023)" in facts and not _polls(facts)
    assert _poll(1, "brak").text.strip() == ""  # the line disappears


def test_endless_waiting_ends_in_a_stated_failure_with_the_retry_button(monkeypatch) -> None:
    _seasons_calls(monkeypatch, [("waiting", {}, "")])
    text = _poll(12).text
    assert FAILED_SENTENCE.format("pobieranie trwa dłużej niż zwykle") in text
    assert "Spróbuj ponownie" in text and "hx-post=" in text and "hx-get=" not in text
    assert "/raport/stan-roslin/ponow?" in text
    assert "Pobieranie zdjęcia satelitarnego…" not in text


def test_missing_at_once_names_the_cause(monkeypatch) -> None:
    reason = f"{background.FAILED_PREFIX} (usługa nie odpowiada)"
    _seasons_calls(monkeypatch, [("missing", {}, reason)])
    text = _poll(1).text
    assert FAILED_SENTENCE.format("usługa nie odpowiada") in text and "Spróbuj ponownie" in text
    brak = _poll(1, "brak").text
    assert NOT_COUNTED_PLANTS in brak and not _polls(brak)


def test_without_network_the_gap_has_no_retry_button(monkeypatch) -> None:
    _seasons_calls(
        monkeypatch, [("missing", {}, "brak kopii zdjęć tej działki i brak połączenia z internetem")]
    )
    text = _poll(1).text
    assert "brak połączenia z internetem" in text and "Spróbuj ponownie" not in text


def test_failed_report_row_keeps_the_gap_in_the_line_of_what_is_not_counted(monkeypatch) -> None:
    gap = CropCondition(state="missing", words="Brak", reason=f"{background.FAILED_PREFIX} (koniec czasu)")
    monkeypatch.setattr("app.report.assess_crop_condition", lambda ctx: gap)
    page = html()
    assert FAILED_SENTENCE.format("koniec czasu") in page and "Spróbuj ponownie" in page
    assert (
        "stan roślin ze zdjęcia satelitarnego" in page.split('id="jeszcze-nie-liczymy"')[1].split("</p>")[0]
    )


def test_retry_button_starts_the_thread_again_at_most_three_times(monkeypatch, parcel) -> None:
    release = threading.Event()
    started: list[int] = []

    def broken(p, year, until=None, deadline=None):
        started.append(year)
        release.wait(5)
        raise RuntimeError("usługa nie odpowiada")

    monkeypatch.setattr(background, "fetch_season", broken)
    release.set()
    path = f"/raport/stan-roslin/ponow?{query(NO_COPY, miejsce='wiersz')}"

    def fail_and_settle() -> None:
        for thread in list(background._running.values()):
            thread.join(5)

    assert background.seasons_for(parcel, main_day())[0] == "waiting"  # attempt 1
    fail_and_settle()
    for attempt in (2, 3):
        answer = client.post(path)
        assert "Pobieranie zdjęcia satelitarnego…" in answer.text, attempt  # a new thread runs
        fail_and_settle()
    last = client.post(path)
    assert "wykorzystano 3 próby" in last.text and "Spróbuj ponownie" not in last.text
    assert len(started) == 3  # one failing season per thread: the limit held
    assert background.attempts_left(parcel.id, main_day()) == 0


def test_retry_while_the_thread_runs_only_resumes_the_polling(monkeypatch) -> None:
    _seasons_calls(monkeypatch, [("waiting", {}, "")])
    monkeypatch.setattr(background, "_running", {background._key("141201_1.0001.77", main_day()): object()})
    answer = client.post(f"/raport/stan-roslin/ponow?{query(NO_COPY, miejsce='wiersz')}")
    assert "Pobieranie zdjęcia satelitarnego…" in answer.text and "proba=1" in answer.text
    assert background.attempts_left("141201_1.0001.77", main_day()) == 3


def test_unknown_place_is_a_404() -> None:
    assert _poll(1, "nigdzie").status_code == 404


def test_the_pdf_of_a_waiting_report_says_the_picture_was_not_ready(monkeypatch) -> None:
    monkeypatch.setattr("app.report.assess_crop_condition", lambda ctx: WAITING)
    page = client.get(f"/raport/druk?{query(DOBRCZ)}").text
    assert "zdjęcie jeszcze się pobiera" in page and NOT_COUNTED_PLANTS not in page


def main_day():
    return date.fromisoformat(DOBRCZ["data"])
