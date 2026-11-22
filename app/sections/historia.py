"""Section 1 "Podatność: 10 sezonów": the crop chosen today on ten seasons of the parcel's weather, by month."""

from __future__ import annotations

from app.advice.diagnosis import SEASONS, SeasonWorst, season_history, season_year
from app.charts.history import history_svg
from app.context import ReportContext
from app.fmt import day_month, dec
from app.models import CROP_LABELS, KeyValue, Section, TextPart, Vulnerability
from app.sections import placeholder
from app.smsr import FIRST_YEAR
from app.smsr.pages import ARCHIVE_DIR, CACHE_DIR, DEMO_DIR, load_page
from app.smsr.parser import SmsrPageError, parse_commune_page

TITLE = "Podatność: 10 sezonów"
MONTHS = {3: "marzec", 4: "kwiecień", 5: "maj", 6: "czerwiec", 7: "lipiec", 8: "sierpień", 9: "wrzesień"}


def smsr_marks(ctx: ReportContext, seasons: list[SeasonWorst]) -> dict[int, str]:
    """SMSR's symbol for the commune in each season since 2020, read only from the pages we already hold.

    A season without a stored page gets no mark: filling the chart would mean up to ten downloads per report.
    """
    soil = ctx.soil.category if ctx.soil else None
    if soil is None:
        return {}
    teryt, label = ctx.parcel.teryt_commune, CROP_LABELS[ctx.request.crop]
    marks: dict[int, str] = {}
    for s in seasons:
        stored = any((d / f"{s.year}_{teryt}.html").exists() for d in (DEMO_DIR, CACHE_DIR, ARCHIVE_DIR))
        if s.year < FIRST_YEAR or not stored:
            continue
        try:
            table = parse_commune_page(load_page(s.year, teryt).html)
        except (SmsrPageError, Exception):
            continue
        symbol = table.symbol(label, soil, s.period.n)
        if symbol:
            marks[s.year] = symbol
    return marks


def _span(seasons: list[SeasonWorst]) -> str:
    return f"{seasons[0].year}–{seasons[-1].year}"


def month_sentence(vuln: Vulnerability) -> str:
    """The split by the month in which a period with a threshold ends, one clause per month."""
    parts = []
    for m in vuln.months:
        deficit = f", średnio o {dec(m.mean_deficit_mm, 1)} mm" if m.mean_deficit_mm is not None else ""
        parts.append(f"{MONTHS[m.month]}: {m.below} z {m.n}{deficit}")
    return "Według miesięcy, w których kończą się okresy z progiem: " + "; ".join(parts) + "."


def build(ctx: ReportContext) -> Section:
    seasons = season_history(ctx)
    if len(seasons) < 2:
        return placeholder(
            "historia",
            TITLE,
            "Brak: bilansu poprzednich sezonów wobec progu, bo mamy dane o pogodzie "
            f"z {len(seasons)} sezonu, a do porównania trzeba co najmniej dwóch.",
        )
    n, current = len(seasons), seasons[-1]
    judged = [s for s in seasons if s.below is not None]
    below = [s for s in judged if s.below]
    marks = smsr_marks(ctx, seasons)
    day = ctx.request.day
    cutoff = day_month(day) if current.year == season_year(ctx) and day.month < 10 else "30.09"
    label = (
        f"Najgorszy okres 60 dni w {n} sezonach {_span(seasons)}: "
        f"{len(below)} z {len(judged)} poniżej progu suszy" if judged else
        f"Najgorszy okres 60 dni w {n} sezonach {_span(seasons)}, bez progu suszy dla tej uprawy"
    )  # fmt: skip

    section = placeholder("historia", TITLE, "")
    section.state, section.reason = "ready", ""
    section.chart_svg = history_svg(seasons, marks, label)
    vuln = ctx.vulnerability
    told = vuln is not None and bool(vuln.sentence)
    if told:
        assert vuln is not None
        section.summary = [TextPart(text=vuln.sentence)]
    elif judged:
        section.summary = [
            TextPart(text="poniżej progu w "),
            TextPart(text=f"{len(below)} z {len(judged)}", bold=True, warn=False),
            TextPart(text=f" sezonów ({_span(seasons)})"),
        ]
    else:
        section.summary = [TextPart(text=f"bez progu suszy w {n} z {n} sezonów ({_span(seasons)})")]
    if judged:
        sentences = [
            f"Poniżej progu suszy był najgorszy okres w {len(below)} z {len(judged)} sezonów z lat {_span(seasons)}."
        ]
    else:
        sentences = [
            f"Dla tej uprawy rozporządzenie nie podaje progu, więc pokazujemy sam bilans {n} sezonów."
        ]
    if vuln is not None and vuln.months:
        sentences = [month_sentence(vuln)]
    ranked = sorted(
        seasons, key=lambda s: s.period.margin_mm if s.period.margin_mm is not None else s.period.kbw_mm
    )
    rank = ranked.index(current) + 1
    sentences.append(
        f"Ten sezon jest {rank}. najgorszy z {n}: bilans {dec(current.period.kbw_mm)} mm w okresie {current.period.n}."
    )
    droughts = [y for y, sym in marks.items() if sym == "+"]
    if marks:
        years = ", ".join(str(y) for y in droughts) or "żaden"
        sentences.append(
            f"SMSR dla gminy {ctx.parcel.commune}: susza w {len(droughts)} z {len(marks)} ocenionych sezonów od {FIRST_YEAR} r. ({years})."
        )
    else:
        sentences.append(
            f"Brak: ocen SMSR gminy {ctx.parcel.commune} dla tych sezonów, bo SMSR publikuje tabele dopiero od {FIRST_YEAR} r. "
            "i nie mamy ich zapisanych."
        )
    section.sentences = sentences
    section.how = (
        f"Dla każdego sezonu brany jest okres 60 dni z najmniejszym zapasem do progu (bilans − próg), do {cutoff} w danym roku, "
        "z tych samych danych o pogodzie i tą samą funkcją co werdykt. Słupek to niedobór w tym okresie (opad − parowanie), "
        "kreska to próg z Dz.U. 2019 poz. 739; kolor mówi, czy słupek sięga progu, a liczba nad słupkiem jest jego wartością. Pod rokiem: ocena SMSR dla gminy (susza albo brak suszy)."
    )
    section.advisor = [
        KeyValue(key="Sezony na wykresie", value=f"{_span(seasons)} ({n} z {SEASONS} możliwych)"),
        KeyValue(
            key="Okres najgorszy w sezonie",
            value=", ".join(
                f"{s.year}: okres {s.period.n}, margines {dec(s.period.margin_mm)} mm" for s in seasons
            )
            if judged
            else "brak progu",
        ),
        KeyValue(
            key="Znaczniki SMSR",
            value=", ".join(f"{y}: {sym}" for y, sym in marks.items()) or "brak zapisanych tabel",
        ),
    ]
    return section
