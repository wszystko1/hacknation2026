"""The visible text of the farmer report does not contradict itself, on every frozen location and demo parcel.

Each check reads the text of all tabs (they are all in the page; the sections are only collapsed) and returns the
contradictions it found as short sentences. A check that finds a real contradiction in today's report is listed
in KNOWN_DEFECTS with the reason, so the test is an expected failure until the text is fixed; every other check
must stay green. `test_a_deliberately_contradictory_text_is_caught` proves the checks can fail.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import BADGE_ABOVE, BADGE_BELOW
from tests.test_locations import BY_NAME, NAMES, _visible_text, use_location  # noqa: F401

DEMO = {
    "demo-dobrcz": {"parcel_id": "040303_2.0002.189/13", "day": "2023-07-20", "crop": "zboza_jare"},
    "demo-gora-sw-malgorzaty": {
        "parcel_id": "100403_2.0011.144",
        "day": "2026-11-21",
        "crop": "rosliny_straczkowe",
    },
}
CASES = [*NAMES, *DEMO]
MONTHS = {
    "stycznia": 1, "lutego": 2, "marca": 3, "kwietnia": 4, "maja": 5, "czerwca": 6,
    "lipca": 7, "sierpnia": 8, "września": 9, "października": 10, "listopada": 11, "grudnia": 12,
}  # fmt: skip
NUM = r"[−-]?\d[\d ]*(?:,\d+)?"
DATE = rf"(\d{{1,2}}) ({'|'.join(MONTHS)}) (\d{{4}})"
ROUND_TOLERANCE = 1.0  # two figures rounded to whole mm may differ by one in a difference


def num(s: str) -> float:
    return float(s.replace("−", "-").replace(" ", "").replace(",", "."))


def parse_date(d: str, m: str, y: str) -> date:
    return date(int(y), MONTHS[m], int(d))


def main_period_text(text: str) -> str:
    """The text without the second method (Doroszewski–Górski) and the worst-period sentences: other periods."""
    text = text.split("werdykt z parowaniem wg doroszewskiego")[0]
    text = re.sub(r"najgorszy okres sezonu do tej pory:[^.]*\.", " ", text)
    return re.sub(r"ten sezon jest \d+\. najgorszy z \d+: bilans [^.]*\.", " ", text)


def one_value(text: str, label: str, pattern: str, group: int = 1) -> list[str]:
    values = {m.group(group).replace(" ", "") for m in re.finditer(pattern, text)}
    return [f"{label}: {', '.join(sorted(values))}"] if len(values) > 1 else []


# (a) slope ---------------------------------------------------------------------------------------------------


def check_slope(text: str, **_: object) -> list[str]:
    if "nie jest wyznaczony" not in text:
        return []
    out = []
    for pat in (r"teren jest nachylony", r"spadek terenu \d", r"spadek średni \d", r"spadek działki \d"):
        if re.search(pat, text):
            out.append(f"«nie jest wyznaczony» obok «{pat}»")
    if "najbliższy rów w odległości 0," in text:
        out.append("odległość do rowu bez modelu terenu")
    return out


# (b) balance, threshold, margin, rainfall, evaporation, usual values ---------------------------------------------


def check_numbers(text: str, **_: object) -> list[str]:
    t = main_period_text(text)
    out: list[str] = []
    out += one_value(
        t, "bilans", rf"bilans (?:wynosi )?({NUM}) mm(?! poniżej| powyżej)(?: wobec| w tym|:|,|\.)"
    )
    out += one_value(t, "próg", rf"(?:wobec progu|(?<!bilans wody i )próg suszy|próg) ({NUM}) mm")
    out += one_value(t, "bilans zwykle", r"zwykle (−\d+) mm")
    out += one_value(t, "opad teraz", r"(?:opad w tym okresie zwykle \d+ mm teraz|spadło|a spadło) (\d+) mm")
    out += one_value(t, "opad zwykle", r"(?:opad w tym okresie zwykle|mniej niż zwykle \() ?(\d+)")
    out += one_value(
        t, "parowanie teraz", r"(?:parowanie w tym okresie zwykle \d+ mm teraz|wyparowało) (\d+) mm"
    )
    out += one_value(t, "parowanie zwykle", r"(?:parowanie w tym okresie zwykle|więcej niż zwykle \() ?(\d+)")
    bal, thr = re.search(rf"bilans ({NUM}) mm wobec progu ({NUM}) mm", t), None
    if bal:
        b, thr = num(bal.group(1)), num(bal.group(2))
        m = re.search(r"o (\d+) mm (gorszy|lepszy) niż próg", t)
        if m and abs(abs(b - thr) - float(m.group(1))) > ROUND_TOLERANCE:
            out.append(f"o {m.group(1)} mm od progu, a {b:.0f} wobec {thr:.0f}")
        rain = re.search(r"spadło (\d+) mm", t)
        evap = re.search(r"wyparowało (\d+) mm", t)
        if rain and evap and abs((float(rain.group(1)) - float(evap.group(1))) - b) > ROUND_TOLERANCE:
            out.append(f"opad {rain.group(1)} − parowanie {evap.group(1)} ≠ bilans {b:.0f}")
    for m in re.finditer(r"spadło (\d+) mm, o (\d+) mm mniej niż zwykle \((\d+) mm\)", t):
        if abs(float(m.group(3)) - float(m.group(1)) - float(m.group(2))) > ROUND_TOLERANCE:
            out.append(f"opad: {m.group(3)} − {m.group(1)} ≠ {m.group(2)}")
    for m in re.finditer(r"wyparowało (\d+) mm, o (\d+) mm więcej niż zwykle \((\d+) mm\)", t):
        if abs(float(m.group(1)) - float(m.group(3)) - float(m.group(2))) > ROUND_TOLERANCE:
            out.append(f"parowanie: {m.group(1)} − {m.group(3)} ≠ {m.group(2)}")
    return out


# (c) irrigation dose ---------------------------------------------------------------------------------------------


def check_dose(text: str, **_: object) -> list[str]:
    out = one_value(text, "dawka mm", r"dawka(?: to)?:? (\d+–\d+) mm")
    ha_m = re.search(r"na działkę ([\d,]+) ha", text)
    mm = re.search(r"dawka(?: to)?:? (\d+)–(\d+) mm", text)
    if not (ha_m and mm):
        return out
    ha = num(ha_m.group(1))
    lo, hi = float(mm.group(1)), float(mm.group(2))
    for m in re.finditer(r"(\d[\d ]*\d)–(\d[\d ]*\d) m³", text):
        a, b = num(m.group(1)), num(m.group(2))
        if abs(a - lo * 10 * ha) > 0.01 * a + 1 or abs(b - hi * 10 * ha) > 0.01 * b + 1:
            out.append(f"{m.group(0)} nie pasuje do {lo:.0f}–{hi:.0f} mm na {ha} ha")
    for m in re.finditer(r"dawkuj około (\d+) mm na polew[^.]*\.? ?dla ([\d,]+) ha to (\d[\d ]*\d) m³", text):
        one = float(m.group(1))
        if not lo <= one <= hi:
            out.append(f"polew {m.group(1)} mm poza dawką {lo:.0f}–{hi:.0f} mm")
        if abs(num(m.group(3)) - one * 10 * num(m.group(2))) > 5 * num(m.group(2)):  # «około N mm»: ±0,5 mm
            out.append(f"polew {m.group(1)} mm ≠ {m.group(3)} m³")
    return out


# (d) "N z 10 sezonów" ------------------------------------------------------------------------------------------------


def check_seasons_below_threshold(text: str, **_: object) -> list[str]:
    fractions = {
        f"{m.group(1)} z {m.group(2)}"
        for m in re.finditer(r"(\d+) z (\d+) (?:sezonów|wcześniejszych lat|poniżej progu suszy)", text)
    }
    return [f"liczba sezonów pod progiem: {', '.join(sorted(fractions))}"] if len(fractions) > 1 else []


# (e) dates ---------------------------------------------------------------------------------------------------------


def check_dates(text: str, day: date, **_: object) -> list[str]:
    out = []
    m = re.search(rf"opad minus parowanie, od {DATE} do {DATE}", text)
    if m:
        start, end = parse_date(*m.groups()[:3]), parse_date(*m.groups()[3:])
        if start > end:
            out.append("początek okna po końcu")
        if end > day:
            out.append(f"koniec okna {end} po dacie oceny {day}")
        for k in re.finditer(rf"bilans do {DATE} jest znany", text):
            known = parse_date(*k.groups())
            if known != end:
                out.append(f"«bilans do {known} jest znany», a okno kończy się {end}")
    return out


# (f) badge and "Susza: tak/nie" follow the sign of the margin ----------------------------------------------------


def check_badge(text: str, **_: object) -> list[str]:
    out = []
    m = re.search(rf"bilans ({NUM}) mm wobec progu ({NUM}) mm", main_period_text(text))
    below, above = BADGE_BELOW.lower() in text, BADGE_ABOVE.lower() in text
    if below and above:
        out.append("obie plakietki naraz")
    if "susza: tak" in text and "susza: nie" in text:
        out.append("«Susza: tak» i «Susza: nie» naraz")
    if m and "poza sezonem" not in text[:2500]:
        negative = num(m.group(1)) - num(m.group(2)) < 0
        if negative and (above or "susza: nie" in text or "lepszy niż próg" in text):
            out.append("margines ujemny, a tekst mówi «lepszy / nie»")
        if not negative and (below or "susza: tak" in text or "gorszy niż próg" in text):
            out.append("margines dodatni, a tekst mówi «gorszy / tak»")
    return out


# (g) a photo "after harvest" next to advice "before the critical phase" --------------------------------------------


def check_harvest_advice(text: str, **_: object) -> list[str]:
    if re.search(r"po zbiorze lub pokosie", text) and "przed fazą krytyczną" in text:
        return ["zdjęcie «po zbiorze» obok rady «przed fazą krytyczną»"]
    return []


# (h) no gap message that repeats «Brak:» inside one sentence -----------------------------------------------------


def check_brak(text: str, **_: object) -> list[str]:
    out = [
        f"«brak:» dwa razy w zdaniu: …{m.group(0)[:80]}…"
        for m in re.finditer(r"brak:[^.]{0,160}?\bbrak:", text)
    ]
    return out + (["żargon porażki technicznej: «niż umiemy czytać»"] if "niż umiemy czytać" in text else [])


CHECKS: dict[str, Callable[..., list[str]]] = {
    "a-slope": check_slope,
    "b-numbers": check_numbers,
    "c-dose": check_dose,
    "d-seasons": check_seasons_below_threshold,
    "e-dates": check_dates,
    "f-badge": check_badge,
    "g-harvest-advice": check_harvest_advice,
    "h-brak": check_brak,
}

# Contradictions found in today's report (see docs/notes/ocena-odpowiedzi-rolnik.md); fixing the text turns them green.
_DEFECTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "a-slope": (
        "W2: the map says the slope is not determined while the terrain row and the text give a slope",
        (
            "dobrcz gora-sw-malgorzaty kietrz podkarpackie-podgorze malopolska-wyzyna lubuskie-poza-sezonem "
            "lubelskie-susza pomorskie-rzepak zachodniopomorskie podlaskie-chmiel slaskie-poza-sezonem "
            "dolnoslaskie-tyton demo-dobrcz demo-gora-sw-malgorzaty"
        ).split(),
    ),
    "c-dose": (
        "W5: «dawkuj około N mm na polew» lies outside the dose range given above it",
        (
            "dobrcz gora-sw-malgorzaty malopolska-wyzyna lubuskie-poza-sezonem lubelskie-susza podlaskie-chmiel "
            "slaskie-poza-sezonem demo-dobrcz demo-gora-sw-malgorzaty"
        ).split(),
    ),
    "d-seasons": (
        "W6: the count of seasons under the threshold differs between the plan, the history and the reliability tab",
        "dobrcz gora-sw-malgorzaty lubuskie-poza-sezonem slaskie-poza-sezonem demo-dobrcz demo-gora-sw-malgorzaty".split(),
    ),
    "e-dates": (
        "W1: «bilans do <data> jest znany» and the window end differ from the assessment date",
        "kietrz podkarpackie-podgorze malopolska-wyzyna lubelskie-susza pomorskie-rzepak podlaskie-chmiel dolnoslaskie-tyton".split(),
    ),
    "g-harvest-advice": (
        "W4: the photo is «after harvest» while the plan advises «before the critical phase»",
        ["pomorskie-rzepak"],
    ),
    "h-brak": (
        "W3: the missing-data sentence repeats «Brak:» and says «niż umiemy czytać»",
        "kietrz podkarpackie-podgorze lubuskie-poza-sezonem zachodniopomorskie podlaskie-chmiel dolnoslaskie-tyton".split(),
    ),
}
KNOWN_DEFECTS: dict[tuple[str, str], str] = {
    (check, name): reason for check, (reason, names) in _DEFECTS.items() for name in names
}

_TEXT: dict[str, str] = {}


def _text(name: str) -> str:
    if name not in _TEXT:
        loc = DEMO.get(name) or BY_NAME[name]
        q = urlencode({"dzialka": loc["parcel_id"], "data": loc["day"], "uprawa": loc["crop"]})
        r = TestClient(app).get(f"/raport?{q}")
        assert r.status_code == 200
        _TEXT[name] = _visible_text(r.text)
    return _TEXT[name]


@pytest.mark.parametrize("check", sorted(CHECKS))
@pytest.mark.parametrize("name", CASES)
def test_report_does_not_contradict_itself(name: str, check: str, request: pytest.FixtureRequest) -> None:
    if name in BY_NAME:
        request.getfixturevalue("use_location")(name)
    reason = KNOWN_DEFECTS.get((check, name))
    if reason:
        request.applymarker(pytest.mark.xfail(reason=reason, strict=False))
    loc = DEMO.get(name) or BY_NAME[name]
    problems = CHECKS[check](_text(name), day=date.fromisoformat(loc["day"]))
    assert not problems, "; ".join(problems)


CONTRADICTORY = _visible_text(
    """
    <p>Działka 1/1 · zboża jare 20 lipca 2023</p>
    <p>Bilans jest lepszy niż próg suszy (szacunek dla działki). Susza: tak. Bilans wody jest o 15 mm gorszy niż próg suszy.</p>
    <p>bilans −203 mm wobec progu −188 mm. opad minus parowanie, od 21 maja 2023 do 20 sierpnia 2023</p>
    <p>W tym okresie bilans wynosi −180 mm. Spadło 69 mm, o 61 mm mniej niż zwykle (130 mm). Wyparowało 272 mm.</p>
    <p>Spadek działki nie jest wyznaczony. Teren jest nachylony. Najbliższy rów w odległości 0,7 m.</p>
    <p>Dawka: 20–25 mm. Gdzie / ile: 4 306–5 382 m³ na działkę 21,53 ha. Dawkuj około 19 mm na polew, nie maksimum:
    dla 21,53 ha to 4 036 m³. W 4 z 10 sezonów bilans spadł pod próg. W 0 z 10 wcześniejszych lat nie.</p>
    <p>Bilans do 20 czerwca 2023 jest znany. Brak: oceny, bo brak: danych, niż umiemy czytać.</p>
    <p>Zdjęcie jest po zbiorze lub pokosie. Usuń chwasty przed fazą krytyczną.</p>
    """
)


@pytest.mark.parametrize("check", sorted(CHECKS))
def test_a_deliberately_contradictory_text_is_caught(check: str) -> None:
    assert CHECKS[check](CONTRADICTORY, day=date(2023, 7, 20)), check


def test_a_consistent_text_passes_every_check() -> None:
    text = _visible_text(
        """<p>Bilans jest lepszy niż próg suszy (szacunek dla działki). bilans −80 mm wobec progu −144 mm.
        Bilans wody jest o 64 mm lepszy niż próg suszy. opad minus parowanie, od 21 maja 2023 do 20 lipca 2023.
        Bilans do 20 lipca 2023 jest znany. Dawka: 20–25 mm. Gdzie / ile: 4 306–5 382 m³ na działkę 21,53 ha.
        W 4 z 10 sezonów bilans spadł pod próg.</p>"""
    )
    for check, fn in CHECKS.items():
        assert fn(text, day=date(2023, 7, 20)) == [], check
