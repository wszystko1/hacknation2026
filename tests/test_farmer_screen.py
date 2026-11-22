"""The farmer screen in two levels: level A (#poziom-a) of at most seven items, level B (#poziom-b) of expandable rows.

The advisor view and the print view keep the blocks they had before; the numbers live in level B and there."""

from __future__ import annotations

import re

import pytest

from app.farmer_view import Bar, plain, weather_bar
from app.models import Cause, Diagnosis
from tests.acceptance.helpers import DOBRCZ, GSM_TODAY, html, report

PARCELS = [DOBRCZ, GSM_TODAY]
IDS = ["dobrcz", "gora"]
FORBIDDEN = ("pobranie trwało", "kat. II", "okres 4", "bilans wody w 60 dniach", "Brak: zgodność metody")
ROMAN_DATE = re.compile(
    r"\b(?:I|II|III|IV|V|VI|VII|VIII|IX|X)\.\s?\d{1,2}\b|\b\d{1,2}\.(?:I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII)\b"
)


def text_of(fragment: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment))


def level_a(page: str) -> str:
    m = re.search(r'<section id="poziom-a".*?</section>\s*(?=<section id="poziom-b")', page, flags=re.S)
    assert m, "#poziom-a stands right before #poziom-b"
    return m.group(0)


def level_b(page: str) -> str:
    start = page.index('<section id="poziom-b"')
    return page[start : page.index("<footer", start)]


def level_a_html(page: str) -> str:
    return level_a(page)


def rows_of(page: str) -> list[str]:
    return re.split(r'(?=<section class="b-group")', level_b(page))[1:]


def farmer_text(page: str) -> str:
    """The farmer's report column without the map column (its source panel is a separate component)."""
    main = page[page.index('<main id="tresc"') :]
    # the collapsed "Dla doradcy" row holds the jury's tables and curve; its sentences name soil categories
    main = re.sub(r'<details class="b-row" id="wiersz-dla-doradcy".*?</details>', " ", main, flags=re.S)
    main = re.sub(
        r'<details class="b-row b-nested" id="wiersz-zrodla".*?</details>', " ", main, flags=re.S
    )  # the sources table names "kat. II"
    return text_of(re.sub(r"<(script|style)\b.*?</\1>", " ", main, flags=re.S))


@pytest.mark.parametrize("params", PARCELS, ids=IDS)
def test_removed_texts_are_gone(params: dict) -> None:
    text = farmer_text(html(params))
    for phrase in FORBIDDEN:
        assert phrase not in text, phrase
    assert not re.search(r"\b\d+,\d s\b", text)
    assert not ROMAN_DATE.search(text)
    assert "Brak: " not in text


@pytest.mark.parametrize("params", PARCELS, ids=IDS)
def test_level_a_has_up_to_seven_items_and_the_pdf_button(params: dict) -> None:
    a = level_a(html(params))
    assert 1 <= a.count("data-a-item") <= 7
    text = text_of(a)
    for needed in ("Raport PDF", "Państwowa ocena IUNG dla gminy", "Wiarygodność wyniku:"):
        assert needed in text, needed


def test_header_has_the_date_in_words_and_the_soil_without_a_category_code() -> None:
    a = text_of(level_a(html(DOBRCZ)))
    assert "20 lipca 2023" in a
    assert "gleba podatna na suszę" in a and "kat." not in a


def test_balance_and_threshold_stand_in_one_row_of_level_b() -> None:
    page = html(DOBRCZ)
    balance = next(r for r in rows_of(page) if 'id="wiersz-bilans"' in r)
    # the period ending on the last full dekad (21.V-20.VII), not the worst of the season (21.IV-20.VI: −201 and −154)
    assert "−203" in text_of(balance) and "−188 mm" in text_of(balance)
    assert "od 21 maja 2023 do 20 lipca 2023" in text_of(balance)
    assert "Najgorszy okres sezonu do tej pory: 21 kwietnia 2023–20 czerwca 2023" in text_of(balance)


@pytest.mark.parametrize("params", PARCELS, ids=IDS)
def test_every_row_is_a_visible_section_with_one_heading(params: dict) -> None:
    rows = rows_of(html(params))
    assert len(rows) >= 5
    for row in rows:
        assert row.count("<h3") == 1
        assert not re.match(r"<section[^>]*>\s*<details", row)


def test_verdict_is_coloured_with_a_word_and_out_of_season_is_grey_without_bars() -> None:
    dry = html(DOBRCZ)
    assert (
        "badge--dry" in dry
        and "Bilans poniżej progu suszy (szacunek dla działki)" in dry
        and "a-bars" in level_a(dry)
    )
    grey = level_a(html(GSM_TODAY))
    assert "badge--neutral" in grey and "Poza sezonem" in grey
    assert "a-bars" not in grey and 'id="zdanie-werdyktu"' in grey


def test_bar_shows_usual_and_now_of_the_first_weather_cause() -> None:
    r = report(DOBRCZ)
    bar = weather_bar(r)
    assert bar == Bar("Opad w tym okresie", "130 mm", "69 mm", 100, 53)
    page_bar = text_of(re.search(r'class="a-bars tile".*?</div>\s*</div>', html(DOBRCZ), flags=re.S).group(0))
    assert "zwykle 130 mm" in page_bar and "teraz 69 mm" in page_bar


def test_bar_follows_the_order_of_the_diagnosis_and_drops_out_without_a_weather_cause() -> None:
    r = report(DOBRCZ)
    causes = {c.code: c for c in r.diagnosis.causes}
    evaporation_first = r.model_copy(
        update={"diagnosis": Diagnosis(causes=[causes["duze_parowanie"], causes["malo_opadu"]])}
    )
    assert weather_bar(evaporation_first).label == "Parowanie w tym okresie"
    soil_only = r.model_copy(update={"diagnosis": Diagnosis(causes=[causes["gleba_lekka"]])})
    assert weather_bar(soil_only) is None
    assert (
        weather_bar(r.model_copy(update={"diagnosis": Diagnosis(causes=[Cause(code="splyw", words="x")])}))
        is None
    )


def test_action_one_has_a_pin_and_a_deadline_or_the_promise_to_give_one() -> None:
    a = text_of(level_a(html(DOBRCZ)))
    pin = 'aria-label="Miejsce na mapie: 1"' in level_a_html(html(DOBRCZ))
    first = report(DOBRCZ).action_1
    has_place = first.candidate is not None and first.candidate.geometry is not None
    assert pin is has_place  # the pin only when the candidate has a place on the map
    assert "inezka" not in a
    # "Kiedy" is shown only for a known deadline; an unknown one goes to the last line "Jeszcze nie liczymy"
    # A dated action shows the year; a seasonal one ("przed okresem wegetacji") shows its own words; an unknown one is promised.
    if first.due is not None:
        assert re.search(r"· .*20\d\d", a)
    elif first.when and not first.when.startswith("Brak"):
        assert re.search(r"· \S", a)
    else:
        assert "termin działania nr 1" in text_of(html(DOBRCZ))


@pytest.mark.parametrize("params", PARCELS, ids=IDS)
def test_empty_parts_are_one_closing_line(params: dict) -> None:
    page = html(params)
    text = farmer_text(page)
    assert len(re.findall(r"Nie ujęto w raporcie:", text)) <= 1
    assert page.count('id="jeszcze-nie-liczymy"') <= 1
    assert "Brak:" not in text


def test_above_threshold_is_stated_without_a_double_meaning() -> None:
    from app.models import BADGE_ABOVE

    assert BADGE_ABOVE == "Bilans jest lepszy niż próg suszy (szacunek dla działki)"


def test_plain_turns_codes_into_words() -> None:
    assert plain("do 31.08.2023") == "do 31 sierpnia 2023"
    assert plain("od 21.III do 30.IX") == "od 21 marca do 30 września"
    assert (
        plain("gleba podatna (kat. II); okres 4 i w okresie 7") == "gleba podatna; ten okres i w tym okresie"
    )
    assert plain("okno 60 dni, kat. III") == "okno 60 dni, kategoria III"


def test_default_view_is_the_farmer_view() -> None:
    page = html(DOBRCZ)
    assert page.index('id="poziom-a"') < page.index('id="poziom-b"')
    assert '<div class="advisor"' not in level_a(page)
