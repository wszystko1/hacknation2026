"""The plan section: the timeline to the end of the drought window, the forecast sentences, the numbering."""

from __future__ import annotations

import re
from datetime import date

import pytest

import app.report as report_module
from app.charts import timeline
from app.models import Action, CropGroup, ExceedanceForecast
from app.report import number_actions
from tests.acceptance.helpers import DOBRCZ, GSM_TODAY, client, html, query, report


def action(n: int, group: str = "retencja", due: date | None = None, causes: int = 1) -> Action:
    return Action(
        id=f"a{n}", n=n, group=group, title=f"Działanie {n}", sentence="x 1", cause="c",
        causes=[f"c{i}" for i in range(causes)], when="do terminu", due=due, source="s",
    )  # fmt: skip


def test_timeline_ends_with_the_last_period_that_has_a_threshold() -> None:
    end = timeline.window_end(date(2023, 7, 20), CropGroup.ZBOZA_JARE, "II")
    assert end is not None
    last, n = end
    assert last == date(2023, 8, 10) and n == 9
    assert timeline.window_end(date(2023, 7, 20), CropGroup.INNA, "II") is None


def test_timeline_out_of_season_points_to_next_year() -> None:
    end = timeline.window_end(date(2026, 11, 21), CropGroup.ROSLINY_STRACZKOWE, "II")
    assert end is not None and end[0].year == 2027


def test_timeline_is_sorted_by_due_and_undated_actions_close_it() -> None:
    actions = [action(1), action(2, due=date(2023, 9, 1)), action(3, due=date(2023, 8, 1))]
    entries = timeline.build_entries(actions, (date(2023, 8, 10), 9), [])
    assert [(e.kind, e.n) for e in entries] == [("action", 3), ("end", None), ("action", 2), ("action", 1)]
    assert entries[-1].label == "do terminu"


def test_a_past_date_lists_what_happened_in_periods_ending_after_it() -> None:
    page = html(DOBRCZ, widok="doradca")
    plan = page[page.index('id="plan"') :]
    assert "Okresy kończące się po 20.07.2023" in plan
    assert re.search(r"okres 8: SMSR dla gminy Dobrcz: brak suszy", plan)


def test_numbering_keeps_the_rank_order_inside_a_group() -> None:
    first = action(0, "retencja", causes=3).model_copy(update={"id": "first"})
    second = action(0, "retencja", causes=1).model_copy(update={"id": "second"})
    other = action(0, "uprawa").model_copy(update={"id": "other"})
    numbered = number_actions([first, second, other], [2])
    assert [(a.n, a.id) for a in numbered] == [(1, "first"), (2, "second"), (3, "other")]
    assert [a.in_plan for a in numbered] == [False, True, False]


def test_numbering_puts_actions_due_before_the_season_first_when_out_of_season() -> None:
    late = action(0, "retencja", due=date(2027, 6, 1))
    early = action(0, "nawadnianie", due=date(2026, 12, 15))
    plain = action(0, "uprawa")
    out = number_actions([late, plain, early], [], date(2026, 11, 21))
    assert [a.group for a in out] == ["nawadnianie", "retencja", "uprawa"]
    inside = number_actions([late, plain, early], [], date(2023, 7, 20))
    assert [a.group for a in inside] == ["retencja", "uprawa", "nawadnianie"]


FORECAST = ExceedanceForecast(
    state="ok",
    sentence="W 4 z 10 wcześniejszych lat dalsza pogoda doprowadziła do przekroczenia progu.",
    skill_sentence="Trafność prognozy: 71%, czułość 60%, precyzja 55%; odpowiedź „zawsze częstsza” daje 64%.",
    what_happened="W 2023 r. bilans do końca okresu nie przekroczył progu.",
)


def plan_html(monkeypatch, forecast: ExceedanceForecast, **params: str) -> str:
    monkeypatch.setattr(report_module, "forecast_exceedance", lambda ctx: forecast)
    page = html(DOBRCZ, widok="doradca", **params)
    return page[page.index('id="plan"') :]


def test_plan_shows_forecast_skill_and_what_happened(monkeypatch) -> None:
    plan = plan_html(monkeypatch, FORECAST)
    assert FORECAST.sentence in plan and FORECAST.skill_sentence in plan
    assert "Prognoza a co się stało" in plan and FORECAST.what_happened in plan


def test_plan_without_what_happened_has_no_such_block(monkeypatch) -> None:
    plan = plan_html(monkeypatch, FORECAST.model_copy(update={"what_happened": ""}))
    assert "Prognoza a co się stało" not in plan


def test_plan_with_a_missing_forecast_has_no_forecast_sentence_and_keeps_the_timeline(monkeypatch) -> None:
    plan = plan_html(monkeypatch, ExceedanceForecast(state="missing", sentence="Brak: prognozy, bo x."))
    assert "Brak: prognozy" not in plan and 'class="forecast"' not in plan
    assert 'class="tl"' in plan


def test_plan_with_a_closed_period_shows_only_the_state_sentence(monkeypatch) -> None:
    state = ExceedanceForecast(
        state="period_over", sentence="Okres krytyczny już się skończył.", skill_sentence="x"
    )
    plan = plan_html(monkeypatch, state)
    assert "Okres krytyczny już się skończył." in plan and "trafnosc-prognozy" not in plan


@pytest.mark.parametrize("params", [DOBRCZ, GSM_TODAY])
@pytest.mark.parametrize("path", ["/raport", "/raport/druk"])
def test_plan_section_has_no_promises(params: dict, path: str) -> None:
    page = html(params, path, **({"widok": "doradca"} if path == "/raport" else {}))
    plan = page[page.index('id="plan"') :]
    plan = plan[: plan.index("</section>")]
    assert "Tu pojawi" not in plan


def test_plan_in_the_link_marks_the_timeline_row() -> None:
    page = client.get(f"/raport?{query(DOBRCZ, plan='1', widok='doradca')}").text
    assert re.search(r'<li class="is-planned" data-plan-item="1">', page)


def test_actions_due_before_the_season_have_the_lowest_numbers() -> None:
    r = report(GSM_TODAY)
    start = date(2027, 3, 21)
    early = [a.n for a in r.actions if a.due is not None and a.due < start]
    rest = [a.n for a in r.actions if a.due is None or a.due >= start]
    assert not early or not rest or max(early) < min(rest)
