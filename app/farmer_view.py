"""The farmer's screen in two levels, built from an existing `Report` (no new calculation).

Level A has at most seven items (header, verdict, two bars, action no. 1, confidence, two buttons). Level B is a
list of expandable rows; each number of the report stands in one row. Words the farmer should not meet (category
codes, period numbers, roman dates, fetch times, "Brak:" boxes) are removed here, in one place, not in the sections.
The advisor view and the print view keep rendering the report blocks as before.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Literal
from urllib.parse import quote

from app.drought.kbw import CROP_GENITIVE
from app.fmt import dec
from app.models import BADGE_ABOVE, BADGE_BELOW, Action, Cause, Report

MONTHS_GENITIVE = (
    "stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca",
    "lipca", "sierpnia", "września", "października", "listopada", "grudnia",
)  # fmt: skip
ROMAN = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII")
WEATHER_CAUSES = ("malo_opadu", "duze_parowanie")
NOT_YET = "nie ujęto w raporcie"
NO_DEADLINE = "termin do ustalenia"

Tone = Literal["dry", "ok", "neutral"]


def date_words(d: date) -> str:
    """20 lipca 2023."""
    return f"{d.day} {MONTHS_GENITIVE[d.month - 1]} {d.year}"


def soil_words(report: Report) -> str:
    """The soil in words, without the category code: "gleba podatna na suszę"."""
    return re.sub(r"\s*\(kat\. [IV]+\)", "", report.soil.words)


_NUM_DATE = re.compile(r"\b(\d{1,2})\.(\d{2})\.(\d{4})\b")
_ROMAN_DATE = re.compile(r"\b(\d{1,2})\.(XII|XI|IX|X|VIII|VII|VI|IV|V|III|II|I)\b")
_PERIOD_NUMBER = r"(?:[1-9]|1[0-2])\b(?! dni)"
_PERIOD_IN = re.compile(rf"\bokresie {_PERIOD_NUMBER}")
_PERIOD_OF = re.compile(rf"\bokresu {_PERIOD_NUMBER}")
_PERIOD = re.compile(rf"\b([Oo])kres {_PERIOD_NUMBER}")
_CATEGORY_BRACKET = re.compile(r"\s*\((?:gleba )?kat\. [IV]+\)")
_CATEGORY = re.compile(r"\bkat\. ([IV]+)\b")
_SECONDS = re.compile(r"\s*[·,;]?\s*\b\d+,\d s\b")


def plain(text: str) -> str:
    """Dates in words, no category codes, no period numbers, no fetch times."""
    text = _NUM_DATE.sub(lambda m: date_words(date(int(m[3]), int(m[2]), int(m[1]))), text)
    text = _ROMAN_DATE.sub(lambda m: f"{m[1]} {MONTHS_GENITIVE[ROMAN.index(m[2])]}", text)
    text = _PERIOD_IN.sub("tym okresie", text)
    text = _PERIOD_OF.sub("tego okresu", text)
    text = _PERIOD.sub(lambda m: "Ten okres" if m[1] == "O" else "ten okres", text)
    text = _CATEGORY_BRACKET.sub("", text)
    text = _CATEGORY.sub(r"kategoria \1", text)
    return _SECONDS.sub("", text).strip()


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.;])\s+", text.strip()) if s]


def balance_numbers(report: Report) -> tuple[str, ...]:
    """The two numbers that stand once, in the balance row: "−201 mm" and "−154 mm"."""
    v = report.verdict
    return tuple(f"{dec(x)} mm" for x in (v.kbw_mm, v.threshold_mm) if x is not None)


def calm(text: str, report: Report) -> str:
    """`plain` text without the sentences that repeat the balance or the threshold, and without "Brak:" ones."""
    own = balance_numbers(report)
    kept = [s for s in _sentences(text) if not s.startswith("Brak") and not any(n in s for n in own)]
    return plain(" ".join(kept))


# ---------------------------------------------------------------- level A


@dataclass(frozen=True)
class Header:
    parcel: str
    commune: str
    precinct: str
    crop: str
    day: str
    soil: str
    area: str
    demo_label: str


@dataclass(frozen=True)
class VerdictItem:
    tone: Tone
    word: str  # "Susza: tak"
    sentence: str


@dataclass(frozen=True)
class Bar:
    label: str
    usual: str
    now: str
    usual_pct: int
    now_pct: int


@dataclass(frozen=True)
class DoItem:
    n: int
    title: str
    place: str
    map_url: str
    when: str


def header(report: Report) -> Header:
    p, req = report.parcel, report.request
    return Header(
        parcel=p.number,
        commune=p.commune,
        precinct=p.precinct,
        crop=req.crop.value,
        day=date_words(req.day),
        soil=soil_words(report),
        area=f"{dec(p.area_ha, 2)} ha",
        demo_label=plain(report.data_copy) if report.data_copy else "",
    )


def verdict_item(report: Report) -> VerdictItem:
    v = report.verdict
    genitive = CROP_GENITIVE[report.request.crop]
    if v.state == "below" and v.margin_mm is not None:
        gap = dec(abs(v.margin_mm))
        return VerdictItem(
            "dry",
            BADGE_BELOW,
            f"Bilans wody jest o {gap} mm gorszy niż próg suszy dla {genitive} na tej glebie.",
        )
    if v.state == "above" and v.margin_mm is not None:
        gap = dec(abs(v.margin_mm))
        return VerdictItem(
            "ok",
            BADGE_ABOVE,
            f"Bilans wody jest lepszy niż próg suszy (o {gap} mm) dla {genitive} na tej glebie.",
        )
    if v.state == "out_of_season":
        last = ""
        if v.margin_mm is not None and v.season_year:
            side = "lepszy" if v.margin_mm >= 0 else "gorszy"
            last = (
                f" W sezonie {v.season_year} bilans był o {dec(abs(v.margin_mm))} mm {side} niż próg suszy."
            )
        return VerdictItem(
            "neutral",
            "Poza sezonem",
            f"Susza rolnicza jest oceniana od 21 marca do 30 września, więc na dziś nie jest oceniana.{last}",
        )
    return VerdictItem(
        "neutral", "Szacunek dla działki", plain(v.sentence) or "Nie udało się policzyć bilansu wody."
    )


_USUAL_NOW = re.compile(r"^(?:spadło|wyparowało) ([\d\s  ,]+) mm, .*\(([\d\s  ,]+) mm\)$")


def _mm_value(text: str) -> float:
    return float(re.sub(r"[\s  ]", "", text).replace(",", "."))


def _bar(cause: Cause) -> Bar | None:
    """ "zwykle X, teraz Y" from the words of the first weather cause in the diagnosis."""
    m = _USUAL_NOW.match(cause.words)
    if m is None:
        return None
    now, usual = _mm_value(m[1]), _mm_value(m[2])
    top = max(now, usual) or 1.0
    label = "Opad w tym okresie" if cause.code == "malo_opadu" else "Parowanie w tym okresie"
    return Bar(
        label, f"{m[2].strip()} mm", f"{m[1].strip()} mm", round(100 * usual / top), round(100 * now / top)
    )


def weather_bars(report: Report) -> list[Bar]:
    """Rain and evaporation bars, "usually / now", for the summary tiles; none out of season."""
    if report.verdict.state in ("out_of_season", "no_data", "no_threshold"):
        return []
    found = [_bar(c) for c in report.diagnosis.causes if c.code in WEATHER_CAUSES]
    return [b for b in found if b is not None]


def todo_items(report: Report) -> list[DoItem]:
    """The one to three most urgent actions, earliest deadline first, for the "Co robić" tile."""
    acts = sorted(report.actions, key=lambda a: (a.due is None, a.due or date.max, a.n))[:3]
    return [DoItem(a.n, a.title, "", map_url(a), when_words(a)) for a in acts]


def weather_bar(report: Report) -> Bar | None:
    """The first cause of the weather axis (too little rain or high evaporation); none out of season."""
    if report.verdict.state in ("out_of_season", "no_data", "no_threshold"):
        return None
    cause = next((c for c in report.diagnosis.causes if c.code in WEATHER_CAUSES), None)
    return _bar(cause) if cause else None


def map_url(action: Action) -> str:
    if action.place is None:
        return ""
    return f"https://www.openstreetmap.org/?mlat={action.place.lat:.6f}&mlon={action.place.lon:.6f}#map=18/{action.place.lat:.6f}/{action.place.lon:.6f}"


def when_words(action: Action) -> str:
    return plain(action.when) if action.when and not action.when.startswith("Brak") else NO_DEADLINE


def do_item(report: Report) -> DoItem | None:
    a = report.action_1
    if a is None:
        return None
    place = a.place.description if a.place else a.no_place_reason
    return DoItem(a.n, a.title, plain(place), map_url(a), when_words(a))


def confidence(report: Report) -> list[str]:
    """Our estimate against the IUNG assessment of the commune, then the sentence that decides for a claim."""
    s = report.smsr
    if s.state == "ok":
        first = f"Państwowa ocena IUNG dla gminy {s.commune}: {plain(s.words).split(',')[0]}."
    else:
        reason = plain(s.reason)
        first = reason if reason.startswith("Brak") else f"Brak oceny IUNG dla gminy {s.commune} w tym okresie: {reason}"
    lines = [first]
    a = report.agreement
    if a.available and a.k_per_100 is not None:
        level = "wysoka" if a.k_per_100 >= 85 else "średnia" if a.k_per_100 >= 60 else "niska"
        lines.append(
            f"Wiarygodność wyniku: {level}. Przy takim wyniku państwowa ocena IUNG potwierdza suszę w {a.k_per_100} na 100 przypadków."
        )
    return lines


# ---------------------------------------------------------------- level B


@dataclass(frozen=True)
class Line:
    """One item of a row: a numbered action or a plain statement."""

    text: str
    n: int | None = None
    note: str = ""
    due: str = ""
    plan_switch: bool = False
    planned: bool = False
    pin: bool = False
    fields: list[tuple[str, str]] = field(default_factory=list)  # labelled bullets of an action card


@dataclass
class Row:
    id: str
    title: str
    paragraphs: list[str] = field(default_factory=list)
    lines: list[Line] = field(default_factory=list)
    kind: Literal["text", "balance", "plan", "gmina", "plants"] = "text"
    failed: bool = False  # kind "plants": the fetch failed for good (still listed in "Nie ujęto w raporcie")

    @property
    def present(self) -> bool:
        return self.kind in ("balance", "gmina", "plants") or bool(self.paragraphs or self.lines)


_DOSE = re.compile(r"\s*\(([^()]*m³[^()]*)\)")
_DEADLINE = re.compile(r"\s*Termin:.*$")


FLAT_WHERE = "Teren płaski: działanie dotyczy całej działki, bez wskazywania jednego miejsca."


def _card_fields(a: Action, text: str, effect: str) -> list[tuple[str, str]]:
    """The bullets of an action card in the order of the map legend: effect, where, how much, risk and time, formality."""
    text = _DEADLINE.sub("", text).strip()
    doses = _DOSE.findall(text)
    text = _DOSE.sub("", text).strip()
    fields = [("Efekt", effect or text)] if (effect or text) else []
    if a.place is not None:
        fields.append(("Gdzie", plain(a.place.description) if a.place.description else plain(a.place.kind)))
    elif "teren płaski" in a.no_place_reason:
        fields.append(("Gdzie", FLAT_WHERE))
    else:
        fields.append(("Gdzie", "cała działka"))
    candidate = a.candidate
    ranges = (
        "; ".join(
            f"{k.replace('_', ' ')} {dec_range(r.low, r.high)} {r.unit}" for k, r in candidate.parameters.items()
        )
        if candidate and candidate.parameters
        else ""
    )
    if doses or ranges:
        fields.append(("Ile", doses[0] if doses else ranges))
    when = plain(a.when) if a.when and not a.when.startswith("Brak") else ""
    risk_list = [*(candidate.risks if candidate and candidate.risks else []), *a.risk_lines]
    risks = "; ".join(risk_list)
    risk_when = " · ".join(x for x in (risks, f"termin: {when}" if when else "") if x)
    if risk_when:
        fields.append(("Ryzyko i termin", risk_when))
    if a.not_when:
        fields.append(("Nie stosuj, gdy", a.not_when))
    if a.next_step:
        fields.append(("Następny krok", a.next_step))
    if a.legal is not None:
        fields.append(
            (
                "Formalność",
                f"{a.legal.formality}, {a.legal.article}" if a.legal.article else str(a.legal.formality),
            )
        )
    return fields[:7]


def dec_range(low: float, high: float) -> str:
    def one(x: float) -> str:
        return dec(x, 0 if float(x).is_integer() else 1)

    return one(low) if low == high else f"{one(low)}–{one(high)}"


def _action_line(a: Action, report: Report, *, plan_switch: bool = False) -> Line:
    """An action with its sentence; the plan row shows only the title and the deadline."""
    text = calm(a.sentence, report)
    effect = plain(a.effect) if a.effect else ""
    if plan_switch:
        due = f"do {date_words(a.due)}" if a.due else when_words(a)
        return Line(a.title, n=a.n, due=due, plan_switch=True, planned=a.in_plan, pin=a.place is not None)
    return Line(a.title, n=a.n, pin=a.place is not None, fields=_card_fields(a, text, effect))


def _balance_row(report: Report) -> Row:
    """The balance and the threshold, once; the worst period of the season beside it; out of season also the rain
    since 1 October against the norm."""
    off = report.off_season
    paragraphs = [plain(off.sentence)] if off and off.sentence else []
    context = getattr(report.verdict, "context", "")
    if context:
        paragraphs.append(plain(context))
    return Row("bilans", "Bilans wody i próg suszy", paragraphs=paragraphs, kind="balance")


CAUSE_LABELS = {
    "malo_opadu": "Za mało opadu",
    "duze_parowanie": "Duże parowanie",
    "gleba_lekka": "Gleba słabo trzyma wodę",
    "splyw": "Woda spływa z pola",
    "faza_wrazliwa": "Uprawa w wrażliwej fazie",
}
PHASE_WORDS = "rozporządzenie podaje dla tej uprawy próg w tym okresie; susza obniża tu plon"


def _causes_row(report: Report) -> Row:
    lines = [
        Line(f"{CAUSE_LABELS[c.code]}: {PHASE_WORDS if c.code == 'faza_wrazliwa' else calm(c.words, report)}")
        for c in report.diagnosis.causes
    ]
    return Row("dlaczego", "Dlaczego tak wyszło", lines=lines)


MONTHS_LOCATIVE = {
    3: "marcu",
    4: "kwietniu",
    5: "maju",
    6: "czerwcu",
    7: "lipcu",
    8: "sierpniu",
    9: "wrześniu",
}


def _frequency_row(report: Report) -> Row:
    v = report.vulnerability
    paragraphs = [plain(v.sentence)] if v.sentence else []
    worst = sorted((m for m in v.months if m.below), key=lambda m: (-m.below, m.month))[:2]
    if worst and all(m.month in MONTHS_LOCATIVE for m in worst):
        names = " i ".join(
            MONTHS_LOCATIVE[m.month]
            for m in sorted(worst, key=lambda m: m.month)
            if m.month in MONTHS_LOCATIVE
        )
        paragraphs.append(f"Najczęściej brakuje wody w {names}: to wtedy najlepiej zaplanować zabieg.")
    return Row("czesto", "Jak często ta działka cierpi", paragraphs=paragraphs)


def _evaporation_row(report: Report) -> Row:
    p = report.verdict.period
    if p is None or report.verdict.state in ("no_data",):
        return Row("parowanie", "Parowanie")
    text = f"W tym okresie wyparowało {dec(p.et0_mm)} mm, a spadło {dec(p.precip_mm)} mm."
    return Row("parowanie", "Parowanie", paragraphs=[text])


def plants_paragraphs(report: Report) -> list[str]:
    """The sentences of the plants row once the picture has been read."""
    c = report.crop_condition
    paragraphs: list[str] = []
    if c.state in ("ok", "not_applicable") and c.words:
        paragraphs.append(plain(c.words))
        if c.scene_date and c.state == "ok":
            paragraphs.append(f"Zdjęcie satelitarne z {date_words(c.scene_date)}.")
        if report.reading:
            paragraphs.append(plain(report.reading))
    return paragraphs


def _plants_row(report: Report) -> Row:
    """While the picture is fetched (or after a failed fetch) the row is the block of app/crop_condition/view.py;
    it polls for itself and swaps itself for the finished sentences."""
    from app.crop_condition.view import from_condition

    block = from_condition(report.crop_condition, report.request, "wiersz")
    if block is not None:
        return Row("rosliny", "Stan roślin ze zdjęcia satelitarnego", kind="plants", failed=block["state"] == "failed")
    return Row("rosliny", "Stan roślin ze zdjęcia satelitarnego", paragraphs=plants_paragraphs(report))


def _plan_row(report: Report) -> Row:
    plan = report.section("plan")
    paragraphs = []
    f = report.forecast
    if f.state != "missing" and f.sentence:
        paragraphs.append(calm(f.sentence, report))
    if plan.state == "missing" and not report.actions:
        return Row("plan", "Plan działań z osią czasu", kind="plan")
    dated = sorted((a for a in report.actions if a.due), key=lambda a: a.due or date.max)
    undated = [a for a in report.actions if not a.due]
    lines = [_action_line(a, report, plan_switch=True) for a in [*dated, *undated]]
    return Row("plan", "Plan działań z osią czasu", paragraphs=paragraphs, lines=lines, kind="plan")


def _crop_actions_row(report: Report) -> Row:
    acts = [a for a in report.actions if a.group == "uprawa"]
    return Row("zabiegi", "Zabiegi w uprawie", lines=[_action_line(a, report) for a in acts])


def _irrigation_row(report: Report) -> Row:
    acts = [a for a in report.actions if a.group == "nawadnianie"]
    return Row("nawadnianie", "Czy nawadniać", lines=[_action_line(a, report) for a in acts])


def _formalities_row(report: Report) -> Row:
    lines = []
    for a in report.actions:
        if a.legal is None:
            continue
        where = f"{a.legal.act}, {a.legal.article}" if a.legal.article else a.legal.act
        lines.append(Line(f"{a.title}: {a.legal.formality} ({where})", n=a.n))
    return Row("formalnosci", "Formalności", lines=lines)


CHART_WORDS = re.compile(
    r"wykres|słupek|kolumn", re.I
)  # sentences about charts the farmer screen does not draw
METHOD_SECTIONS = ("retencja", "uprawa", "plan", "nawadnianie")


def _method_row(report: Report) -> Row:
    """How actions and the forecast are chosen; the balance itself is explained in its own row."""
    paragraphs = [
        "Bilans to opad minus parowanie w 60 dniach; próg suszy pochodzi z rozporządzenia (Dz.U. 2019 poz. 739).",
    ]
    texts = [s.how for s in report.sections if s.how and s.id in METHOD_SECTIONS]
    paragraphs += [t for t in (calm(x, report) for x in texts) if t and not CHART_WORDS.search(t)]
    paragraphs.append(plain(report.verdict.disclaimer) + ".")
    paragraphs.append(
        "Raport nie uwzględnia drenowania, wód gruntowych ani faktycznej daty siewu."
    )  # task 3.3.5
    return Row("jak", "Jak powstał wynik", paragraphs=paragraphs)


def _slope_row(report: Report) -> Row:
    runoff = next((c for c in report.diagnosis.causes if c.code == "splyw"), None)
    reason = plain(report.map.runoff_reason) if report.map and report.map.runoff_reason else ""
    # "slope not determined" must not stand beside a determined slope
    paragraphs = [reason] if reason and not (runoff and "nie jest wyznaczony" in reason) else []
    if runoff:
        paragraphs.append(f"Teren jest nachylony: {calm(runoff.words, report)}.")
    lines = [_action_line(a, report) for a in report.actions if a.group == "retencja"]
    return Row("spadek", "Spadek terenu i miejsca na wodę", paragraphs=paragraphs, lines=lines)


def _commune_row(report: Report) -> Row:
    return Row("gmina", "Gmina: ocena IUNG i trafność metody", kind="gmina")


ROW_BUILDERS = (
    _balance_row, _causes_row, _frequency_row, _evaporation_row, _plants_row, _plan_row,
    _crop_actions_row, _irrigation_row, _formalities_row, _method_row, _slope_row, _commune_row,
)  # fmt: skip


def rows(report: Report) -> list[Row]:
    return [row for build in ROW_BUILDERS for row in [build(report)]]


def not_counted(all_rows: list[Row]) -> str:
    """ "Nie ujęto w raporcie: …" with the names of the rows that have nothing to show; "" when none is empty."""
    # a plants row that is still being fetched is not "not counted" yet; one that failed for good is
    names = [row.title.lower() for row in all_rows if not row.present or row.id == "rosliny" and row.failed]
    return f"Nie ujęto w raporcie: {', '.join(names)}." if names else ""


@dataclass
class FarmerView:
    header: Header
    verdict: VerdictItem
    bar: Bar | None
    do: DoItem | None
    bars: list[Bar]
    todo: list[DoItem]
    dots: int | None
    season_line: str
    confidence: list[str]
    rows: list[Row]
    missing_line: str
    pdf_query: str
    advisor_query: str
    commune_measures: dict[str, str]
    balance_caption: str
    plants_pending: bool = False  # the satellite picture is still being fetched (the PDF says so)


def _query(report: Report) -> str:
    r = report.request
    plan = f"&plan={','.join(map(str, r.plan))}" if r.plan else ""
    return f"dzialka={quote(r.parcel_id, safe='')}&data={r.day.isoformat()}&uprawa={r.crop.value}{plan}"


def commune_measures(report: Report) -> dict[str, str]:
    a = report.agreement
    if not a.available or a.accuracy is None or a.accuracy_majority is None:
        return {}
    return {
        "accuracy": f"{dec(100 * a.accuracy, 1)}%",
        "majority": f"{dec(100 * a.accuracy_majority, 1)}%",
    }


def balance_caption(report: Report) -> str:
    """ "opad minus parowanie, od 21 kwietnia do 20 czerwca 2023" for the number in the balance row."""
    p = report.verdict.period
    if p is None:
        return ""
    note = f"; {plain(report.verdict.note)}" if report.verdict.note else ""
    day = report.request.day
    if report.verdict.state in ("below", "above", "no_threshold") and p.end < day:
        note = f"; okno kończy się na ostatniej pełnej dekadzie przed {date_words(day)}{note}"
    return f"opad minus parowanie, od {date_words(p.start)} do {date_words(p.end)}{note}"


def build(report: Report) -> FarmerView:
    all_rows = rows(report)
    query = _query(report)
    do = do_item(report)
    missing = not_counted(all_rows)
    if do is not None and do.when == NO_DEADLINE:
        # the "Kiedy" line shows only a known deadline; an unknown one goes to the last line
        missing = (
            (missing[:-1] + ", termin działania nr 1.")
            if missing
            else "Nie ujęto w raporcie: termin działania nr 1."
        )
    return FarmerView(
        header=header(report),
        verdict=verdict_item(report),
        bar=weather_bar(report),
        do=do,
        bars=weather_bars(report),
        todo=todo_items(report),
        dots=round(report.agreement.k_per_100 / 10)
        if report.agreement.available and report.agreement.k_per_100 is not None
        else None,
        season_line=plain(report.vulnerability.sentence),
        confidence=confidence(report),
        rows=[r for r in all_rows if r.present],
        missing_line=missing,
        pdf_query=query,
        advisor_query=f"{query}&widok=doradca",
        commune_measures=commune_measures(report),
        balance_caption=balance_caption(report),
        plants_pending=any(r.kind == "plants" and not r.failed for r in all_rows),
    )
