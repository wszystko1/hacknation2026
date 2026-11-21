"""Rules on indicators for soil and crop management and for irrigation (retention lives in app.advice.retention).

An action comes from one catalogue row (app/advice/catalog.csv). It appears only when
  1. one of the causes of its row was diagnosed for the parcel (`Action.causes` lists the words of every such cause), and
  2. the row's conditions (`cond_*` columns) and the crop rules below fit the parcel.
The sentence is the row's fixed sentence with this parcel's numbers; the term is computed from the assessment date.

Thresholds that stand in this file and not in a source are the team's proposals (`PROPOSALS`); the adviser view
lists them as such. The water balance of the root zone (FAO-56, chapter 8) is not computed: irrigation is decided
from the crop phase and the climatic water balance against the regulation's threshold.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

from app.advice.catalog import CatalogRow, effect_text, load_catalog, rank_actions
from app.advice.diagnosis import SEASONS, _cached, season_year
from app.advice.legal import legal_note
from app.context import ReportContext
from app.drought.kbw import PERIODS, period_dates, season_of
from app.drought.thresholds import threshold_mm
from app.fmt import day, day_month, dec
from app.models import CROP_LABELS, Action, CropGroup, SoilCategory

GROUPS = ("uprawa", "nawadnianie")
MIN_DATA_SHARE = 0.9  # a period needs this share of days with rain and evaporation to count

# Rows we do not turn into actions, with the reason (shown to the adviser).
NOT_USED: dict[str, str] = {
    "nawadnianie-termin-fao56": "wymaga bilansu wody w strefie korzeni, którego nie liczymy",
}

# Sown crops only; perennials are planted once, so sowing, catch crops and ploughing rules do not apply to them.
PERENNIAL = (CropGroup.DRZEWA_OWOCOWE, CropGroup.KRZEWY_OWOCOWE, CropGroup.TRUSKAWKI, CropGroup.CHMIEL)
SOWING_ACTIONS = (
    "miedzyplon",
    "uprawa-uproszczona",
    "rezygnacja-z-orki-wiosennej",
    "termin-siewu",
    "odmiany-tolerancyjne",
)
AUTUMN_SOWN = (CropGroup.ZBOZA_OZIME, CropGroup.RZEPAK)  # no spring ploughing before sowing
EARLY_HARVEST = (CropGroup.ZBOZA_OZIME, CropGroup.ZBOZA_JARE, CropGroup.RZEPAK, CropGroup.ROSLINY_STRACZKOWE)

KNOWN_CONDITIONS = ("soil", "dose_share_of_max")

# Terms and doses we propose (no source states them); the adviser view prints this table.
PROPOSALS: tuple[tuple[str, str], ...] = (
    ("Koniec zbioru zbóż, rzepaku i roślin strączkowych", "31.VIII; innych upraw 15.X"),
    ("Siew ozimin i rzepaku / jarych i okopowych", "20.IX / 10.IV"),
    ("Okno siewu międzyplonu po żniwach", "do 31.VIII, potem do 15.IX i 30.IX"),
    ("Nawadnianie „teraz tak”", "bilans KBW okresu poniżej progu z rozporządzenia, uprawa w fazie z progiem"),
    (
        "Dawka na glebie IV",
        "jak na średniej (30–35 mm); poradnik podaje dawki tylko dla gleb lekkich i średnich",
    ),
)

# CDR 2025, p. 244: dose on light and on medium soils, mm.
DOSE_LIGHT = (20, 25)
DOSE_MEDIUM = (30, 35)
M3_PER_HA_PER_MM = 10
PERMIT_M3_PER_YEAR = 5 * 365  # 5 m³ per day on average over the year (Prawo wodne, art. 34 pkt 12)

WATER_KIND = {"ditch": "rów", "stream": "ciek", "canal": "kanał", "water_body": "zbiornik wodny"}


# ---------------------------------------------------------------- the weather by period and decade


@dataclass(frozen=True)
class PeriodSum:
    """The balance of one regulation period in one season, summed over days that have data."""

    year: int
    n: int
    kbw_mm: float
    complete: bool  # the period ended on or before the day counted for that season
    enough_data: bool


def _by_day(ctx: ReportContext) -> dict[str, tuple[float, float]]:
    def compute() -> dict[str, tuple[float, float]]:
        w = ctx.data.weather.data if ctx.data.weather.usable else None
        if w is None:
            return {}
        return {
            d: (p, e)
            for d, p, e in zip(w.dates, w.precipitation_mm, w.et0_mm, strict=True)
            if p is not None and e is not None
        }

    return _cached(ctx, "agro_by_day", compute)


def _sum_days(ctx: ReportContext, start: date, stop: date) -> tuple[float, float, int]:
    """(rain, evaporation, days with data) from `start` to `stop` inclusive."""
    by_day = _by_day(ctx)
    rain = et0 = 0.0
    days = 0
    d = start
    while d <= stop:
        if (pair := by_day.get(d.isoformat())) is not None:
            rain += pair[0]
            et0 += pair[1]
            days += 1
        d += timedelta(days=1)
    return rain, et0, days


def _until(ctx: ReportContext, year: int) -> date:
    """The last day counted in `year`: the assessment day's date, or 30.IX out of season."""
    d = ctx.request.day
    return (
        date(year, d.month, min(d.day, calendar.monthrange(year, d.month)[1]))
        if season_of(d)[1]
        else date(year, 9, 30)
    )


def period_sums(ctx: ReportContext) -> list[PeriodSum]:
    """Every period of the last SEASONS seasons that started by the counted day, from the same weather as the verdict."""

    def compute() -> list[PeriodSum]:
        out: list[PeriodSum] = []
        last = season_year(ctx)
        for year in range(last - SEASONS + 1, last + 1):
            until = _until(ctx, year)
            for n, _, _ in PERIODS:
                start, end = period_dates(year, n)
                if start > until:
                    continue
                stop = min(end, until)
                rain, et0, days = _sum_days(ctx, start, stop)
                window = (stop - start).days + 1
                out.append(
                    PeriodSum(year, n, round(rain - et0, 1), end <= until, days >= MIN_DATA_SHARE * window)
                )
        return out

    return _cached(ctx, "agro_period_sums", compute)


def _soil(ctx: ReportContext) -> SoilCategory | None:
    return ctx.soil.category if ctx.soil else None


def seasons_below(ctx: ReportContext, crop: CropGroup, soil: SoilCategory | None) -> tuple[int, int]:
    """(seasons with a finished period under the crop's threshold, seasons judged) on the parcel's weather."""
    if soil is None:
        return 0, 0
    judged: set[int] = set()
    below: set[int] = set()
    for p in period_sums(ctx):
        thr = threshold_mm(crop, soil, p.n)
        if thr is None or not p.complete or not p.enough_data:
            continue
        judged.add(p.year)
        if p.kbw_mm < thr:
            below.add(p.year)
    return len(below), len(judged)


# Order of the comparison: the crops a farmer most often weighs against each other.
COMPARED = (
    CropGroup.ZBOZA_OZIME,
    CropGroup.ZBOZA_JARE,
    CropGroup.RZEPAK,
    CropGroup.ZIEMNIAK,
    CropGroup.KUKURYDZA_ZIARNO,
    CropGroup.BURAK_CUKROWY,
)
COMPARED_MAX = 3


def crop_comparison(ctx: ReportContext) -> list[tuple[CropGroup, int, int]]:
    """(crop, seasons under the threshold, seasons judged) for the chosen crop first, then up to three others.

    The same weather and the same soil category, only the thresholds differ. Crops without a threshold on this soil
    (the regulation prints "-" or "x" in every period) are left out.
    """
    soil = _soil(ctx)
    crop = ctx.request.crop
    rows: list[tuple[CropGroup, int, int]] = []
    for c in (crop, *[c for c in COMPARED if c != crop]):
        k, n = seasons_below(ctx, c, soil)
        if n:
            rows.append((c, k, n))
        if len(rows) > COMPARED_MAX:
            break
    return rows


@dataclass(frozen=True)
class Decade:
    """One of the 18 decades of IV-IX; `end` is its last day."""

    index: int  # 0..17
    month: int
    part: int  # 1..3
    start: date
    end: date


def decades(year: int) -> list[Decade]:
    out: list[Decade] = []
    for i in range(18):
        month, part = 4 + i // 3, i % 3 + 1
        last = calendar.monthrange(year, month)[1]
        start_day = 1 + 10 * (part - 1)
        end_day = 10 * part if part < 3 else last
        out.append(Decade(i, month, part, date(year, month, start_day), date(year, month, end_day)))
    return out


@dataclass(frozen=True)
class DecadeCount:
    decade: Decade
    period_n: int | None  # the period that ends on this decade's last day; None: no period ends here
    below: int
    judged: int  # seasons with a finished, complete period; 0 when the regulation gives no threshold


def decade_counts(ctx: ReportContext) -> list[DecadeCount]:
    """For every decade IV-IX: in how many seasons the 60-day window ending on it was under the threshold."""
    soil, crop = _soil(ctx), ctx.request.crop
    ends = {period_dates(2001, n)[1].replace(year=2001): n for n, _, _ in PERIODS}
    sums = {(p.year, p.n): p for p in period_sums(ctx)}
    years = sorted({p.year for p in sums.values()})
    out: list[DecadeCount] = []
    for d in decades(season_year(ctx)):
        n = ends.get(d.end.replace(year=2001))
        thr = threshold_mm(crop, soil, n) if soil is not None and n is not None else None
        below = judged = 0
        if n is not None and thr is not None:
            for y in years:
                p = sums.get((y, n))
                if p is None or not p.complete or not p.enough_data:
                    continue
                judged += 1
                below += p.kbw_mm < thr
        out.append(DecadeCount(d, n, below, judged))
    return out


@dataclass(frozen=True)
class DecadeDeficit:
    decade: Decade
    deficit_mm: float | None  # evaporation minus rain; None: not counted yet or too few days with data
    sensitive: bool  # a period with a threshold for this crop and soil covers the whole decade


def decade_deficits(ctx: ReportContext) -> list[DecadeDeficit]:
    """Shortfall (evaporation − rain) per decade of the season shown, against the crop's phases with a threshold."""
    soil, crop = _soil(ctx), ctx.request.crop
    year = season_year(ctx)
    until = _until(ctx, year)
    out: list[DecadeDeficit] = []
    for d in decades(year):
        sensitive = False
        if soil is not None:
            for n, _, _ in PERIODS:
                start, end = period_dates(year, n)
                if start <= d.start and d.end <= end and threshold_mm(crop, soil, n) is not None:
                    sensitive = True
        value: float | None = None
        if d.end <= until:
            rain, et0, days = _sum_days(ctx, d.start, d.end)
            if days >= MIN_DATA_SHARE * ((d.end - d.start).days + 1):
                value = round(et0 - rain, 1)
        out.append(DecadeDeficit(d, value, sensitive))
    return out


# ---------------------------------------------------------------- irrigation: now yes or no


@dataclass(frozen=True)
class Irrigation:
    now: bool | None  # None: cannot be judged
    reason: str  # one sentence with the parcel's numbers
    dose_mm: tuple[int, int] | None
    dose_m3: tuple[int, int] | None


def dose_range(soil: SoilCategory | None) -> tuple[int, int] | None:
    if soil is None:
        return None
    return DOSE_LIGHT if soil in ("I", "II") else DOSE_MEDIUM


def irrigation(ctx: ReportContext) -> Irrigation:
    """ "Teraz tak" when the finished or running period is under the regulation's threshold; "teraz nie" otherwise."""
    v, soil, crop = ctx.verdict, _soil(ctx), ctx.request.crop
    dose = dose_range(soil)
    m3 = (
        (
            round(dose[0] * M3_PER_HA_PER_MM * ctx.parcel.area_ha),
            round(dose[1] * M3_PER_HA_PER_MM * ctx.parcel.area_ha),
        )
        if dose
        else None
    )

    def result(now: bool | None, reason: str) -> Irrigation:
        return Irrigation(now, reason, dose, m3)

    if v is None or v.state == "no_data" or v.period is None:
        return result(None, "Brak: decyzji o nawadnianiu, bo nie ma oceny bilansu dla tej działki.")
    if v.state == "out_of_season":
        return result(
            False,
            "Teraz nie: jest poza okresem monitoringu suszy (21.III–30.IX), więc nie ma bilansu, który wskazywałby brak wody.",
        )
    if crop == CropGroup.INNA or soil is None:
        return result(
            None, "Brak: decyzji o nawadnianiu, bo dla innej uprawy albo nieznanej gleby nie mamy progu."
        )
    p = v.period
    if p.threshold_mm is None:
        return result(
            False,
            f"Teraz nie: w okresie {p.n} ({day_month(p.start)}–{day_month(p.end)}) rozporządzenie nie podaje progu dla tej uprawy "
            "na tej glebie, czyli susza nie obniża w tej fazie plonu.",
        )
    gap = dec(abs(p.kbw_mm - p.threshold_mm))
    running = "" if p.complete else " (okres jeszcze trwa)"
    if p.kbw_mm < p.threshold_mm:
        return result(
            True,
            f"Teraz tak: bilans {dec(p.kbw_mm)} mm w okresie {p.n} ({day_month(p.start)}–{day_month(p.end)}){running} jest "
            f"{gap} mm poniżej progu {dec(p.threshold_mm)} mm, a uprawa jest w fazie, w której susza obniża plon.",
        )
    return result(
        False,
        f"Teraz nie: bilans {dec(p.kbw_mm)} mm w okresie {p.n} ({day_month(p.start)}–{day_month(p.end)}){running} jest "
        f"{gap} mm nad progiem {dec(p.threshold_mm)} mm.",
    )


def _range(pair: tuple[int, int]) -> str:
    return f"{dec(pair[0])}–{dec(pair[1])}" if pair[0] != pair[1] else dec(pair[0])


def water_source_sentence(ctx: ReportContext) -> str:
    """The nearest surface water from BDOT10k, as the possible source of irrigation water."""
    water = ctx.data.water.data if ctx.data.water.usable else None
    if water is None:
        return "Brak: źródła wody do nawadniania z BDOT10k, bo warstwy wód nie udało się pobrać."
    if water.nearest_any_m is None or water.nearest_any_kind is None:
        return (
            f"W promieniu {dec(water.search_m)} m od działki BDOT10k nie ma rowu, cieku ani zbiornika, "
            "więc wodę trzeba by dowieźć albo pobrać z ujęcia."
        )
    kind = WATER_KIND.get(water.nearest_any_kind, "woda powierzchniowa")
    where = "przy granicy działki" if water.nearest_any_m < 1 else f"{dec(water.nearest_any_m)} m od działki"
    return (
        f"Najbliższe źródło wody to {kind} {where} (BDOT10k); pobór z niego podlega przepisom o poborze wody."
    )


# ---------------------------------------------------------------- terms


def _by(today: date, *month_days: tuple[int, int]) -> date:
    """The first of the given calendar days that is not before `today`; the first of them next year otherwise."""
    for year in (today.year, today.year + 1):
        for m, d in month_days:
            if (candidate := date(year, m, d)) >= today:
                return candidate
    raise AssertionError("unreachable")


def _spring(ctx: ReportContext) -> date:
    """The last day before the monitoring season that follows the assessment day (20.III)."""
    d = ctx.request.day
    return date(d.year + 1 if d.month >= 10 else d.year, 3, 20)


def _sowing(ctx: ReportContext) -> date:
    d = ctx.request.day
    if ctx.request.crop in AUTUMN_SOWN:
        return _by(d, (9, 20))
    return _by(d, (4, 10))


def _after_harvest(ctx: ReportContext) -> date:
    d, crop = ctx.request.day, ctx.request.crop
    return _by(d, (8, 31) if crop in EARLY_HARVEST else (10, 15), (10, 31))


def _due(row: CatalogRow, ctx: ReportContext, now: bool | None) -> date | None:
    """The deadline that places the action on the timeline; None when the action has no calendar date."""
    d, in_season = ctx.request.day, bool(ctx.verdict and ctx.verdict.state != "out_of_season")
    match row.action_id:
        case "mulczowanie":
            return _spring(ctx) if not in_season else _after_harvest(ctx)
        case "miedzyplon":
            return _by(d, (8, 31), (9, 15), (9, 30))
        case "zielona-okrywa-miedzyrzedzi":
            return _by(d, (4, 30), (9, 30))
        case "uprawa-uproszczona" | "termin-siewu":
            return _sowing(ctx)
        case "rezygnacja-z-orki-wiosennej":
            return _by(d, (4, 10))
        case "gleboszowanie" | "gleboszowanie-sciezek":
            return _by(d, (10, 31))
        case "materia-organiczna":
            return _by(d, (11, 15))
        case "odchwaszczanie-w-suszy":
            return d + timedelta(days=10) if in_season else _by(d, (4, 20))
        case "odmiany-tolerancyjne":
            return _sowing(ctx) - timedelta(days=30)
        case "pobor-wody-nawadnianie":
            if now:
                return d
            return None if in_season else _spring(ctx)
        case "nawadnianie-uzupelniajace":
            return d if now else None
    return None


def _when(row: CatalogRow, due: date | None, now: bool | None, in_season: bool) -> str:
    if row.action_id == "mulczowanie" and not in_season:
        return f"resztki po zbiorze zostaw na polu przez zimę, do {day(due)}"
    if row.action_id == "nawadnianie-uzupelniajace":
        if now:
            return f"teraz, do {day(due)}"
        return "gdy bilans okresu spadnie poniżej progu, w sezonie 21.III–30.IX"
    return f"{row.term}, do {day(due)}" if due else row.term


# ---------------------------------------------------------------- actions


def _source(row: CatalogRow) -> str:
    doc = row.source_doc.split(",")[0].split(";")[0].strip()
    parts = [doc]
    if row.source_page:
        parts.append(f"s. {row.source_page}")
    if row.confidence not in doc:
        parts.append(row.confidence)
    return " · ".join(parts)


def _applies(row: CatalogRow, ctx: ReportContext) -> bool:
    if row.action_id in NOT_USED:
        return False
    if any(v and k not in KNOWN_CONDITIONS for k, v in row.conditions.items()):
        return False  # a condition this code cannot check must not be skipped silently
    allowed = row.cond_set("soil")
    if allowed and _soil(ctx) not in allowed:
        return False
    crop = ctx.request.crop
    if row.action_id in SOWING_ACTIONS and crop in PERENNIAL:
        return False
    if row.action_id == "rezygnacja-z-orki-wiosennej" and crop in AUTUMN_SOWN:
        return False
    return True


def _soil_words(ctx: ReportContext) -> str:
    soil = _soil(ctx)
    return f"kategorii {soil}" if soil else "o nieznanej kategorii"


def _sentence(row: CatalogRow, ctx: ReportContext, ir: Irrigation) -> str:
    v = ctx.verdict
    deficit = max(0.0, -v.kbw_mm) if v and v.kbw_mm is not None else 0.0
    area = ctx.parcel.area_ha
    dose_mm = dose_m3 = ""
    if ir.dose_mm and ir.dose_m3:
        dose_mm, dose_m3 = _range(ir.dose_mm), _range(ir.dose_m3)
        share = row.cond("dose_share_of_max")
        if share is not None:  # one dose "about 0.75 of the maximum" instead of the range
            dose_mm = dec(share * ir.dose_mm[1])
            dose_m3 = dec(share * ir.dose_mm[1] * M3_PER_HA_PER_MM * area)
    fields = {
        "area_ha": dec(area, 2),
        "soil": _soil_words(ctx),
        "deficit_mm": dec(deficit),
        "dose_mm": dose_mm,
        "dose_m3": dose_m3,
        "term": row.term,
    }
    if row.action_id == "nawadnianie-uzupelniajace":
        if ir.now is None:
            return ir.reason
        dose = f"{dose_mm} mm ({dose_m3} m³ na działkę {dec(area, 2)} ha)"
        lead = (
            f"{ir.reason} Dawka: {dose}."
            if ir.now
            else f"{ir.reason} Gdy bilans spadnie poniżej progu, dawka to {dose}."
        )
        return lead
    return row.sentence.format_map(fields)


def field_actions(ctx: ReportContext) -> list[Action]:
    """Soil, crop and irrigation actions for the diagnosed causes; at most three per group, best first."""
    diagnosis = ctx.diagnosis
    if diagnosis is None or not diagnosis.causes or ctx.verdict is None:
        return []
    ir = irrigation(ctx)
    found: list[Action] = []
    for row in load_catalog().values():
        if row.group not in GROUPS or not _applies(row, ctx):
            continue
        matched = [c.words for c in diagnosis.causes if c.code in row.causes]
        if not matched:
            continue
        due = _due(row, ctx, ir.now)
        title = row.title
        if row.action_id == "nawadnianie-uzupelniajace" and ir.now is not None:
            title = f"Teraz {'tak' if ir.now else 'nie'}: {row.title[:1].lower()}{row.title[1:]}"
        crop_gate = (
            row.action_id == "nawadnianie-uzupelniajace" and ctx.request.crop != CropGroup.BURAK_CUKROWY
        )
        found.append(
            Action(
                id=row.action_id,
                n=0,
                group=row.group,
                title=title,
                sentence=_sentence(row, ctx, ir),
                cause=matched[0],
                causes=matched,
                effect="" if crop_gate else effect_text(row),
                when=_when(row, due, ir.now, ctx.verdict.state != "out_of_season"),
                due=due,
                source=_source(row),
                legal=legal_note(row.action_id) if row.legal_article else None,
            )
        )
    return rank_actions(found, ctx.request.day)


def crop_label(crop: CropGroup) -> str:
    label = CROP_LABELS[crop]
    return label[:1].lower() + label[1:]
