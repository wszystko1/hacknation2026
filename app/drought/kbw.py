"""Climatic water balance (KBW) in the 14 periods of the drought regulation (Dz.U. 2019 poz. 739).

KBW = sum of precipitation - sum of reference evapotranspiration (ET0, FAO-56) over one period of six dekads.
The verdict compares the KBW of each finished period with the threshold for the crop group and soil category.
"""

from __future__ import annotations

import calendar
import os
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Literal

from app.drought.thresholds import threshold_cell, threshold_mm
from app.fmt import day as ddmmyyyy
from app.fmt import dec
from app.models import (
    BADGE_ABOVE,
    BADGE_BELOW,
    LAW_THRESHOLDS,
    SOIL_CATEGORIES,
    CropGroup,
    PeriodBalance,
    SoilCategory,
    Verdict,
)

# Switches read at every call, so a running server and a test can flip them without a restart.
VERDICT_PERIOD_ENV = (
    "CHRONPLON_VERDICT_PERIOD"  # "current" (default): the period ending on the last full dekad
)
VERDICT_ET_ENV = "CHRONPLON_VERDICT_ET"  # "dg" (default) or "fao56": the evaporation formula of the verdict


def verdict_period_mode() -> Literal["current", "worst"]:
    """Which period the verdict is about: "current" (default) or "worst" (the earlier behaviour, smallest margin)."""
    return "worst" if os.environ.get(VERDICT_PERIOD_ENV, "").strip().lower() == "worst" else "current"


def verdict_et_method() -> Literal["fao56", "dg"]:
    """Evaporation formula of the verdict: Doroszewski-Górski unless the switch says "fao56"."""
    return "fao56" if os.environ.get(VERDICT_ET_ENV, "").strip().lower() == "fao56" else "dg"


# A period with more than this share of days without precipitation or ET0 does not enter the verdict.
MAX_MISSING_SHARE = 0.10

# Genitive of the crop group names, for "próg suszy dla zbóż jarych".
CROP_GENITIVE: dict[CropGroup, str] = {
    CropGroup.BURAK_CUKROWY: "buraka cukrowego",
    CropGroup.CHMIEL: "chmielu",
    CropGroup.DRZEWA_OWOCOWE: "drzew owocowych",
    CropGroup.KRZEWY_OWOCOWE: "krzewów owocowych",
    CropGroup.KUKURYDZA_KISZONKA: "kukurydzy na kiszonkę",
    CropGroup.KUKURYDZA_ZIARNO: "kukurydzy na ziarno",
    CropGroup.ROSLINY_STRACZKOWE: "roślin strączkowych",
    CropGroup.RZEPAK: "rzepaku i rzepiku",
    CropGroup.TRUSKAWKI: "truskawek",
    CropGroup.TYTON: "tytoniu",
    CropGroup.WARZYWA: "warzyw gruntowych",
    CropGroup.ZBOZA_JARE: "zbóż jarych",
    CropGroup.ZBOZA_OZIME: "zbóż ozimych",
    CropGroup.ZIEMNIAK: "ziemniaka",
    CropGroup.INNA: "innej uprawy",
}

# (period number, (start month, day), (end month, day)) as published by SMSR IUNG.
PERIODS: list[tuple[int, tuple[int, int], tuple[int, int]]] = [
    (1, (3, 21), (5, 20)),
    (2, (4, 1), (5, 31)),
    (3, (4, 11), (6, 10)),
    (4, (4, 21), (6, 20)),
    (5, (5, 1), (6, 30)),
    (6, (5, 11), (7, 10)),
    (7, (5, 21), (7, 20)),
    (8, (6, 1), (7, 31)),
    (9, (6, 11), (8, 10)),
    (10, (6, 21), (8, 20)),
    (11, (7, 1), (8, 31)),
    (12, (7, 11), (9, 10)),
    (13, (7, 21), (9, 20)),
    (14, (8, 1), (9, 30)),
]


def period_dates(year: int, n: int) -> tuple[date, date]:
    _, (sm, sd), (em, ed) = PERIODS[n - 1]
    return date(year, sm, sd), date(year, em, ed)


def period_length(year: int, n: int) -> int:
    start, end = period_dates(year, n)
    return (end - start).days + 1


def last_full_dekad_end(day: date) -> date:
    """End of the last dekad (1-10, 11-20, 21-end of month) that is complete on `day`, `day` included."""
    last = calendar.monthrange(day.year, day.month)[1]
    if day.day >= last:
        return date(day.year, day.month, last)
    if day.day >= 20:
        return date(day.year, day.month, 20)
    if day.day >= 10:
        return date(day.year, day.month, 10)
    prev = day.replace(day=1) - timedelta(days=1)
    return prev


def season_of(day: date) -> tuple[int, bool]:
    """(season year, in_monitoring) for a day: 21.III-30.IX is in the monitoring period."""
    if date(day.year, 3, 21) <= day <= date(day.year, 9, 30):
        return day.year, True
    return (day.year if day.month >= 10 else day.year - 1), False


def period_balance(
    dates: Sequence[str],
    precip: Sequence[float | None],
    et0: Sequence[float | None],
    year: int,
    n: int,
    until: date,
    crop: CropGroup,
    soil: SoilCategory | None,
) -> PeriodBalance | None:
    """KBW of period n in `year`, summed up to min(period end, until). None when the period has not started."""
    start, end = period_dates(year, n)
    stop = min(end, until)
    if stop < start:
        return None
    by_day = {d: (p, e) for d, p, e in zip(dates, precip, et0, strict=True)}
    p_sum = e_sum = 0.0
    days = 0
    d = start
    while d <= stop:
        p, e = by_day.get(d.isoformat(), (None, None))
        if p is not None and e is not None:
            p_sum += p
            e_sum += e
            days += 1
        d += timedelta(days=1)
    kbw = round(p_sum - e_sum, 1)
    thr = threshold_mm(crop, soil, n) if soil else None
    return PeriodBalance(
        n=n,
        start=start,
        end=end,
        precip_mm=round(p_sum, 1),
        et0_mm=round(e_sum, 1),
        kbw_mm=kbw,
        threshold_mm=thr,
        margin_mm=round(kbw - thr, 1) if thr is not None else None,
        complete=end <= until,
        days=days,
    )


def season_balances(
    dates: Sequence[str],
    precip: Sequence[float | None],
    et0: Sequence[float | None],
    year: int,
    until: date,
    crop: CropGroup,
    soil: SoilCategory | None,
) -> list[PeriodBalance]:
    out = []
    for n, _, _ in PERIODS:
        pb = period_balance(dates, precip, et0, year, n, until, crop, soil)
        if pb is not None:
            out.append(pb)
    return out


def _span(p: PeriodBalance) -> str:
    return f"{ddmmyyyy(p.start)}–{ddmmyyyy(p.end)}"


def _missing_days(p: PeriodBalance, until: date) -> tuple[int, int]:
    """(days without precipitation or ET0, days in the window so far)."""
    window = (min(p.end, until) - p.start).days + 1
    return window - p.days, window


def _usable(p: PeriodBalance, until: date) -> bool:
    missing, window = _missing_days(p, until)
    return missing <= MAX_MISSING_SHARE * window


def _water(kbw: float) -> str:
    """How rain and evaporation compare, in words."""
    if round(kbw) < 0:
        return f"wyparowało o {dec(-kbw)} mm więcej wody, niż spadło"
    if round(kbw) > 0:
        return f"spadło o {dec(kbw)} mm więcej wody, niż wyparowało"
    return "spadło tyle wody, ile wyparowało"


def _against_threshold(margin: float, crop: CropGroup) -> str:
    target = f"progu suszy dla {CROP_GENITIVE[crop]} na tej glebie"
    if round(margin) == 0:
        return f"To bilans równy {target}."
    side = "poniżej" if margin < 0 else "powyżej"
    return f"To {dec(abs(margin))} mm {side} {target}."


def _no_threshold_reason(crop: CropGroup, soil: SoilCategory | None, periods: list[PeriodBalance]) -> str:
    """Why the regulation gives no threshold for the shown periods, as one sentence."""
    if crop == CropGroup.INNA:
        return f"Dla uprawy spoza 14 grup („Inna uprawa”) {LAW_THRESHOLDS} nie podaje progu suszy, więc pokazujemy sam bilans."
    if soil is None:
        return "Bez kategorii gleby nie wybierzemy progu suszy, więc pokazujemy sam bilans."
    cells = {threshold_cell(crop, soil, p.n) for p in periods}
    if cells == {"-"}:
        return (
            f"Na glebie kat. {soil} rozporządzenie nie zaleca uprawy {CROP_GENITIVE[crop]} "
            f"(„-” w tabeli {LAW_THRESHOLDS}), więc nie ma progu suszy."
        )
    return (
        f"W tych okresach susza nie obniża plonu {CROP_GENITIVE[crop]} („x” w tabeli {LAW_THRESHOLDS}), "
        "więc nie ma progu suszy."
    )


def _soil_range(crop: CropGroup, p: PeriodBalance) -> str:
    """Thresholds of the shown period for categories I..IV, when the parcel's soil category is unknown."""
    values = [(c, threshold_mm(crop, c, p.n)) for c in SOIL_CATEGORIES]
    known = [(c, t) for c, t in values if t is not None]
    if not known:
        return _no_threshold_reason(crop, "I", [p])
    below = [c for c, t in known if p.kbw_mm < t]
    (c1, t1), (c2, t2) = known[0], known[-1]
    tail = (
        f"bilans jest poniżej progu na glebie kat. {', '.join(below)}"
        if below
        else "bilans jest lepszy niż próg na każdej glebie"
    )
    return (
        f"Bez kategorii gleby nie wybierzemy progu: dla {CROP_GENITIVE[crop]} w tym okresie to od "
        f"{dec(t1)} mm (kat. {c1}) do {dec(t2)} mm (kat. {c2}); {tail}."
    )


def _neighbour_note(crop: CropGroup, neighbour: SoilCategory, periods: list[PeriodBalance]) -> str:
    margins = [
        (round(p.kbw_mm - t, 1), p) for p in periods if (t := threshold_mm(crop, neighbour, p.n)) is not None
    ]
    if not margins:
        return f"Przy sąsiedniej kategorii gleby (kat. {neighbour}) rozporządzenie nie daje progu."
    margin, p = min(margins, key=lambda m: m[0])
    side = "poniżej progu" if margin < 0 else "lepiej niż próg"
    return (
        f"Przy sąsiedniej kategorii gleby (kat. {neighbour}): {dec(abs(margin))} mm {side} "
        f"(okres {p.n}, {_span(p)})."
    )


def _no_data(sentence: str, periods: list[PeriodBalance] | None = None, note: str = "") -> PeriodVerdict:
    return PeriodVerdict(
        state="no_data",
        badge="",
        kbw_mm=None,
        threshold_mm=None,
        margin_mm=None,
        period=None,
        periods=periods or [],
        sentence=sentence,
        how="",
        note=note,
    )


class PeriodVerdict(Verdict):
    """`Verdict` that also keeps the worst period of the season so far and the line that sets it beside the shown one."""

    worst: PeriodBalance | None = None  # smallest margin among the usable finished periods with a threshold
    context: str = ""  # "Najgorszy okres sezonu do tej pory: ..." or "" when the shown period is the worst


def _current_period(usable: list[PeriodBalance], with_thr: list[PeriodBalance]) -> PeriodBalance:
    """The period that ends on the last full dekad; the latest one with a threshold when the crop has none now.

    Crops with a late or short critical period (potatoes from period 3, maize from 4, cereals up to 9) have
    no threshold in the period that ends today, so the verdict stays on the last one that has it.
    """
    latest = max(usable, key=lambda p: p.n)
    if latest.margin_mm is not None or not with_thr:
        return latest
    return max(with_thr, key=lambda p: p.n)


def _context_line(top: PeriodBalance, worst: PeriodBalance | None, until: date, crop: CropGroup) -> str:
    """One line: the worst period of the season so far beside the shown one, and why the shown one is not latest."""
    parts = []
    if top.end < until:
        parts.append(
            f"Okres kończący się {ddmmyyyy(until)} nie ma progu suszy dla {CROP_GENITIVE[crop]}, "
            f"więc werdykt dotyczy ostatniego okresu z progiem: {_span(top)}."
        )
    if worst is not None and worst.n != top.n and worst.margin_mm is not None:
        side = "poniżej" if worst.margin_mm < 0 else "powyżej"
        parts.append(
            f"Najgorszy okres sezonu do tej pory: {_span(worst)}, bilans {dec(worst.kbw_mm)} mm, "
            f"{dec(abs(worst.margin_mm))} mm {side} progu."
        )
    return " ".join(parts)


def assess(
    dates: Sequence[str],
    precip: Sequence[float | None],
    et0: Sequence[float | None],
    day: date,
    crop: CropGroup,
    soil: SoilCategory | None,
    *,
    neighbour: SoilCategory | None = None,
    et_method: Literal["fao56", "dg"] = "fao56",
    period: Literal["current", "worst"] | None = None,
) -> PeriodVerdict:
    """The verdict for the analysis day by the definition of Dz.U. 2019 poz. 739.

    `et0` is the series of the evaporation formula named by `et_method` (the caller computes it). The running
    window ends on the last full dekad, as SMSR IUNG counts it: on 15.V it is 21.III-10.V (51 days).

    Every finished period of the season is compared with the threshold for the crop group and soil category.
    `period="worst"` (the default here) shows the period with the smallest margin (KBW - threshold);
    `period="current"` shows the period that ends on the last full dekad, as SMSR IUNG reports it, and keeps the
    worst period of the season so far in `worst`. The report takes the choice from `main_verdict`, which reads the
    switch. Out of season the worst period of the season is shown either way.
    Periods with more than 10% of days without weather data are left out and named in `note`.
    """
    verdict = _assess(dates, precip, et0, day, crop, soil, neighbour, period or "worst")
    if et_method == "dg":
        how = f"{verdict.how} · parowanie wzorem Doroszewskiego–Górskiego" if verdict.how else ""
        return verdict.model_copy(update={"et_method": "dg", "how": how})
    return verdict


def main_verdict(
    dates: Sequence[str],
    precip: Sequence[float | None],
    et0: Sequence[float | None],
    day: date,
    crop: CropGroup,
    soil: SoilCategory | None,
    *,
    neighbour: SoilCategory | None = None,
) -> PeriodVerdict:
    """The FAO-56 verdict, period chosen by the switch. The report and the waiting page take their verdict from
    `app.drought.variants.main_verdict`, which uses this one as the fallback and as the second variant."""
    return assess(
        dates,
        precip,
        et0,
        day,
        crop,
        soil,
        neighbour=neighbour,
        et_method="fao56",
        period=verdict_period_mode(),
    )


def _assess(
    dates: Sequence[str],
    precip: Sequence[float | None],
    et0: Sequence[float | None],
    day: date,
    crop: CropGroup,
    soil: SoilCategory | None,
    neighbour: SoilCategory | None,
    mode: Literal["current", "worst"],
) -> PeriodVerdict:
    if not dates:
        return _no_data(
            "Brak: bilansu wody, bo nie ma danych o pogodzie dla tej działki; "
            "spróbuj za minutę albo wybierz inną datę."
        )
    year, in_season = season_of(day)
    until = last_full_dekad_end(day) if in_season else date(year, 9, 30)
    raw = season_balances(dates, precip, et0, year, until, crop, soil)
    # Only periods that can enter the verdict are checked: finished ones, or the running first period.
    gaps = [p for p in raw if (p.complete or p.n == 1) and not _usable(p, until)]
    periods = [p.model_copy(update={"margin_mm": None}) if p in gaps else p for p in raw]
    gap_note = " ".join(
        f"Okres {p.n} pominięty: brak opadu albo parowania w {m} z {w} dni."
        for p in gaps
        for m, w in [_missing_days(p, until)]
    )

    complete = [p for p in periods if p.complete]
    if not complete:
        running = periods[0] if periods else None
        if running is None:  # 21-30 March: the first dekad of the season is not complete yet
            return _no_data(
                "Brak: bilansu wody, bo pierwsza dekada okresu monitoringu (21–31 marca) jeszcze się nie zakończyła."
            )
        elapsed = (until - running.start).days + 1
        return PeriodVerdict(
            state="running",
            badge="",
            kbw_mm=running.kbw_mm,
            threshold_mm=None,
            margin_mm=None,
            period=running,
            periods=periods,
            sentence=(
                f"Od {ddmmyyyy(running.start)} {_water(running.kbw_mm)}. Pierwszy okres 60 dni jeszcze trwa; "
                f"wynik wobec progu suszy podamy po {ddmmyyyy(running.end)}."
            ),
            how=(
                f"opad {dec(running.precip_mm)} − parowanie {dec(running.et0_mm)} = {dec(running.kbw_mm)} mm "
                f"({ddmmyyyy(running.start)}–{ddmmyyyy(until)}) · definicja z {LAW_THRESHOLDS}"
            ),
            note=" ".join(
                x
                for x in [f"okres jeszcze trwa: {elapsed} z {period_length(year, running.n)} dni", gap_note]
                if x
            ),
        )

    usable = [p for p in complete if _usable(p, until)]
    if not usable:
        return _no_data(
            "Brak: wyniku wobec progu, bo w każdym zakończonym okresie brakuje ponad 10% dni "
            "z opadem albo parowaniem.",
            periods,
            gap_note,
        )
    with_thr = [p for p in usable if p.margin_mm is not None]
    worst = min(with_thr, key=lambda p: p.margin_mm) if with_thr else None
    top = worst if worst else min(usable, key=lambda p: p.kbw_mm)
    if in_season and mode == "current":
        top = _current_period(usable, with_thr)

    if not in_season:
        state, badge = "out_of_season", f"Sezon {year}"
    elif top.margin_mm is None:
        state, badge = "no_threshold", ""
    elif top.margin_mm < 0:
        state, badge = "below", BADGE_BELOW
    else:
        state, badge = "above", BADGE_ABOVE

    if not in_season:
        lead = f"W sezonie {year}, w dniach {_span(top)},"
    elif mode == "current":
        lead = "W tych 60 dniach"
    else:
        lead = "W tych 60 dniach"
    sentence = f"{lead} {_water(top.kbw_mm)}. "
    if top.margin_mm is not None:
        sentence += _against_threshold(top.margin_mm, crop)
    elif soil is None and crop != CropGroup.INNA:
        sentence += _soil_range(crop, top)
    else:
        sentence += _no_threshold_reason(crop, soil, usable)

    how = (
        f"opad {dec(top.precip_mm)} − parowanie {dec(top.et0_mm)} = {dec(top.kbw_mm)} mm "
        f"(okres {top.n}, {_span(top)}) · "
        + (f"próg z {LAW_THRESHOLDS}" if top.threshold_mm is not None else f"definicja z {LAW_THRESHOLDS}")
    )
    notes = [gap_note]
    if neighbour and neighbour != soil and crop != CropGroup.INNA:
        notes.append(_neighbour_note(crop, neighbour, usable))
    return PeriodVerdict(
        state=state,
        badge=badge,
        kbw_mm=top.kbw_mm,
        threshold_mm=top.threshold_mm,
        margin_mm=top.margin_mm,
        period=top,
        periods=periods,
        sentence=sentence,
        how=how,
        season_year=year if not in_season else None,
        note=" ".join(n for n in notes if n),
        worst=worst if in_season else None,
        context=_context_line(top, worst, until, crop) if in_season and mode == "current" else "",
    )
