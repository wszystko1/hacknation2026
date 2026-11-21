"""K2: three separate answers under the badge (verdict, plants, vulnerability), never glued into one number,
and one sentence that reads the verdict and the plants together."""

from __future__ import annotations

import pytest
from markupsafe import escape

from app.models import CropCondition
from tests.acceptance.helpers import html, report

CONFIRMED = "susza potwierdzona przez stan roślin"
LAGGING = "bilans poniżej progu; satelita jeszcze nie pokazuje stresu (wskaźnik reaguje z opóźnieniem)"
UNEXPLAINED = "spadek niewyjaśniony bilansem, sprawdź na polu (lokalny opad nawalny, zalanie, zbiór lub pokos, inna uprawa)"
NO_SIGN = "brak oznak problemu z wodą"
READINGS = (CONFIRMED, LAGGING, UNEXPLAINED, NO_SIGN)


def plants(signal: str | None, **extra: object) -> CropCondition:
    return CropCondition.model_validate(
        {"state": "ok", "words": "rośliny na działce", "signal": signal, "n_seasons": 4} | extra
    )


@pytest.mark.xfail(reason="not built yet", strict=False)
@pytest.mark.parametrize(
    ("verdict", "signal", "text"),
    [("below", "weaker", CONFIRMED), ("below", "normal", LAGGING), ("above", "weaker", UNEXPLAINED),
     ("above", "normal", NO_SIGN)],
)  # fmt: skip
def test_verdict_and_plants_are_read_together(verdict: str, signal: str, text: str) -> None:
    from app.crop_condition import read_together

    assert text in read_together(verdict, plants(signal)).lower()


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_below_threshold_with_normal_plants_does_not_reassure() -> None:
    from app.crop_condition import read_together

    s = read_together("below", plants("normal")).lower()
    for calming in ("brak oznak", "nie ma suszy", "nie ma problemu", "w normie"):
        assert calming not in s


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_no_picture_gives_the_verdict_alone_with_the_gap() -> None:
    from app.crop_condition import read_together

    missing = CropCondition(
        state="missing",
        words="Brak: zdjęcia bez chmur",
        reason="brak zdjęcia bez chmur w 15 dniach przed datą",
    )
    for verdict in ("below", "above"):
        s = read_together(verdict, missing).lower()
        assert "brak" in s
        for text in READINGS:
            assert text not in s


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_picture_after_harvest_or_mowing_is_not_read_as_weaker() -> None:
    from app.crop_condition import read_together

    cut = plants(None, harvest=True, words="zdjęcie po zbiorze lub pokosie: nie ocenia stresu")
    s = read_together("above", cut).lower()
    assert "nie ocenia stresu" in s
    for text in READINGS:
        assert text not in s


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_no_reading_without_a_badge() -> None:
    from app.crop_condition import read_together

    for verdict in ("running", "no_threshold"):
        assert read_together(verdict, plants("weaker")) == ""


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_report_shows_three_separate_answers_and_the_reading_under_the_badge() -> None:
    from app.crop_condition import read_together

    r = report()
    assert r.reading == read_together(r.verdict.state, r.crop_condition)
    page = html()
    top = page[page.index('id="werdykt"') :]
    top = top[: top.index("</section>")]
    for text in (r.crop_condition.words, r.vulnerability.sentence, r.reading):
        if text:
            assert str(escape(text)) in top, text
    assert r.vulnerability.sentence
    for glued in ("score", "risk", "risk_index", "ryzyko", "wskaznik"):
        assert glued not in r.model_dump()
