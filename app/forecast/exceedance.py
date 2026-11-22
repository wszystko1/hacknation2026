"""Chance that KBW falls below the threshold in a period ending between the analysis date and the end of the
critical period (the last period with a threshold for the crop group).

The app method is completion with runs: the balance up to the analysis date is known; the rest of the period is
filled with the weather of the same calendar days of each earlier year (the first 16 days with the Open-Meteo
forecast, when there is one). The label of every run comes from the same KBW code as the verdict
(`app.drought.kbw.period_balance`). It is computed on the fly from the years before the analysis year and keeps
no stored weights. The reference is the historical frequency: how often an earlier year's own weather went below
the threshold. A gradient-boosting model is compared only in `scripts/eval_forecast.py`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta

from app.context import ReportContext
from app.drought.kbw import CROP_GENITIVE, MAX_MISSING_SHARE, period_balance, period_dates
from app.drought.thresholds import threshold_mm
from app.fmt import day, dec, pct
from app.models import CropGroup, ExceedanceForecast, SoilCategory

MIN_YEARS = 5  # fewer earlier years than this is not a frequency
Reading = tuple[float | None, float | None]  # (precipitation mm, ET0 mm) of one day
Daily = Mapping[date, Reading]
NO_READING: Reading = (None, None)


@dataclass(frozen=True)
class Chance:
    """k of n earlier years went below the threshold; `years` are the years that entered."""

    k: int
    n: int
    years: tuple[int, ...] = ()

    @property
    def probability(self) -> float | None:
        return self.k / self.n if self.n else None


def daily_series(
    dates: list[str], precip: list[float | None], et0: list[float | None]
) -> dict[date, Reading]:
    return {date.fromisoformat(d): (p, e) for d, p, e in zip(dates, precip, et0, strict=True)}


def thresholded_periods(crop: CropGroup, soil: SoilCategory | None) -> list[int]:
    """Periods of the regulation that carry a threshold for the crop group on this soil category."""
    if soil is None:
        return []
    return [n for n in range(1, 15) if threshold_mm(crop, soil, n) is not None]


def critical_end(crop: CropGroup, soil: SoilCategory | None, year: int) -> date | None:
    """End of the last period with a threshold: the end of the critical period."""
    periods = thresholded_periods(crop, soil)
    return period_dates(year, max(periods))[1] if periods else None


def _period_below(
    reading: Callable[[date], Reading], year: int, n: int, crop: CropGroup, soil: SoilCategory
) -> bool | None:
    """True when KBW of period n is below its threshold; None when more than 10% of its days are missing."""
    start, end = period_dates(year, n)
    days = [start + timedelta(i) for i in range((end - start).days + 1)]
    values = [reading(d) for d in days]
    balance = period_balance(
        [d.isoformat() for d in days],
        [v[0] for v in values],
        [v[1] for v in values],
        year,
        n,
        end,
        crop,
        soil,
    )
    if balance is None or balance.margin_mm is None or balance.days < (1 - MAX_MISSING_SHARE) * len(days):
        return None
    return balance.margin_mm < 0


def _year_below(
    reading: Callable[[date], Reading], year: int, periods: list[int], crop: CropGroup, soil: SoilCategory
) -> bool | None:
    """Did any of the periods go below its threshold; None when none of them can be judged."""
    results = [r for n in periods if (r := _period_below(reading, year, n, crop, soil)) is not None]
    return any(results) if results else None


def _same_day(d: date, year: int) -> date:
    try:
        return d.replace(year=year)
    except ValueError:  # 29 February
        return d.replace(year=year, day=28)


def completed_run(
    daily: Daily,
    asof: date,
    source_year: int,
    periods: list[int],
    crop: CropGroup,
    soil: SoilCategory,
    overlay: Daily | None = None,
) -> bool | None:
    """One run: the analysis year up to `asof`, then the forecast overlay, then the weather of `source_year`."""
    overlay = overlay or {}

    def reading(d: date) -> Reading:
        if d <= asof:
            return daily.get(d, NO_READING)
        if d in overlay:
            return overlay[d]
        return daily.get(_same_day(d, source_year), NO_READING)

    return _year_below(reading, asof.year, periods, crop, soil)


def own_weather_run(
    daily: Daily, year: int, periods: list[int], crop: CropGroup, soil: SoilCategory
) -> bool | None:
    """What an earlier year did with its own weather (the historical frequency and the validation label)."""
    return _year_below(lambda d: daily.get(d, NO_READING), year, periods, crop, soil)


def periods_after(asof: date, crop: CropGroup, soil: SoilCategory | None) -> list[int]:
    """Periods with a threshold that end after the analysis date (they end by the end of the critical period)."""
    return [n for n in thresholded_periods(crop, soil) if period_dates(asof.year, n)[1] > asof]


def _count(labels: dict[int, bool | None]) -> Chance:
    used = {y: v for y, v in labels.items() if v is not None}
    return Chance(sum(used.values()), len(used), tuple(sorted(used)))


def in_season_chances(
    daily: Daily,
    asof: date,
    crop: CropGroup,
    soil: SoilCategory,
    years: list[int],
    overlay: Daily | None = None,
) -> tuple[Chance, Chance]:
    """(completion with runs, historical frequency) from `years`, all earlier than the analysis year."""
    assert all(y < asof.year for y in years), "an earlier year is needed"
    periods = periods_after(asof, crop, soil)
    runs = {y: completed_run(daily, asof, y, periods, crop, soil, overlay) for y in years}
    own = {y: own_weather_run(daily, y, periods, crop, soil) for y in years}
    return _count(runs), _count(own)


def next_season_chance(daily: Daily, crop: CropGroup, soil: SoilCategory, years: list[int]) -> Chance:
    """Climatology out of season: how often an earlier season went below any threshold of the crop."""
    periods = thresholded_periods(crop, soil)
    return _count({y: own_weather_run(daily, y, periods, crop, soil) for y in years})


# ---------------------------------------------------------------- the report step


def _missing(reason: str) -> ExceedanceForecast:
    return ExceedanceForecast(state="missing", sentence=f"Brak: szansy przekroczenia progu, bo {reason}.")


def _earlier_years(daily: Daily, before: int) -> list[int]:
    first = min((d.year for d in daily), default=before)
    return list(range(first, before))


def _overlay(ctx: ReportContext, asof: date) -> dict[date, Reading]:
    """The model forecast for the days after the analysis date, when it starts right at the date."""
    f = ctx.data.forecast.data if ctx.data.forecast.usable else None
    if f is None or not f.dates or date.fromisoformat(f.dates[0]) > asof + timedelta(days=1):
        return {}
    return {
        date.fromisoformat(d): (p, e)
        for d, p, e in zip(f.dates, f.precipitation_mm, f.et0_mm, strict=False)
        if date.fromisoformat(d) > asof
    }


def _analog_loses(metrics: Mapping[str, object]) -> bool:
    """True when the validation found no skill over the historical frequency (BSS not above zero)."""
    bss = metrics.get("forecast.brier_skill")
    return isinstance(bss, (int, float)) and bss <= 0


def skill_sentence(metrics: Mapping[str, object], method: str) -> str:
    """One sentence for the farmer: accuracy next to the answer "always the more frequent outcome"."""
    suffix = "_hist" if method == "historical" else ""
    acc, maj = metrics.get(f"forecast.accuracy{suffix}"), metrics.get("forecast.accuracy_majority")
    rec, prec = (
        metrics.get(f"forecast.recall{suffix}"),
        metrics.get(f"forecast.precision{suffix}"),
    )
    if not all(isinstance(x, (int, float)) for x in (acc, maj, rec, prec)):
        return "Brak: trafności prognozy, bo walidacja krocząca na latach wcześniejszych nie została jeszcze policzona."
    first, last = metrics.get("forecast.test_year_first"), metrics.get("forecast.test_year_last")
    where = f" na latach {first}–{last}" if first and last else ""
    n = metrics.get("forecast.n_cases")
    cases = f" ({dec(float(n))} przypadków)" if isinstance(n, (int, float)) else ""
    return (
        f"W walidacji{where}{cases} przy szansie od 50% prognoza trafiała w {pct(float(acc))} przypadków "
        f"(odpowiedź „zawsze częstsza odpowiedź” w {pct(float(maj))}), wykrywała {pct(float(rec))} przekroczeń progu, "
        f"a {pct(float(prec))} jej ostrzeżeń się sprawdzało."
    )


def _what_happened(ctx: ReportContext, periods: list[int], soil: SoilCategory, shown: Chance) -> str:
    """For a past date: the balance of the periods ending after it, from the archive, next to the forecast."""
    asof, crop = ctx.request.day, ctx.request.crop
    archive = _archive_series(ctx, asof)
    if archive is None:
        return ""
    last_day = max(archive)
    lines, below = [], 0
    for n in periods:
        start, end = period_dates(asof.year, n)
        if end > last_day:
            continue
        days = [start + timedelta(i) for i in range((end - start).days + 1)]
        values = [archive.get(d, NO_READING) for d in days]
        b = period_balance(
            [d.isoformat() for d in days],
            [v[0] for v in values],
            [v[1] for v in values],
            asof.year,
            n,
            end,
            crop,
            soil,
        )
        if b is None or b.margin_mm is None or b.days < (1 - MAX_MISSING_SHARE) * len(days):
            continue
        under = b.margin_mm < 0
        below += under
        lines.append(
            f"okres {n} (do {day(end)}): bilans {dec(b.kbw_mm)} mm przy progu {dec(b.threshold_mm)} mm, "
            + ("poniżej progu" if under else "powyżej progu")
        )
    if not lines:
        return ""
    chance = f"{pct(shown.probability)} ({shown.k} z {shown.n} lat)" if shown.n else "bez liczby"
    verdict = "próg został przekroczony" if below else "próg nie został przekroczony"
    return f"Prognoza z {day(asof)} dawała szansę {chance}. W archiwum: {'; '.join(lines)}. Zatem {verdict}."


def _archive_series(ctx: ReportContext, asof: date) -> dict[date, Reading] | None:
    """Weather after the analysis date for a past date: the latest committed copy of the parcel that reaches past it."""
    if asof >= date.today():
        return None
    from app.geodata import config, list_samples, load_sample

    # Weather-only copies of later dates live beside the demo copies, so they are not offered as demo dates.
    archive = config.demo_dir() / "archive"
    pid = ctx.data.parcel.data.id
    later = sorted(d for p, d in list_samples(archive) if p == pid and d > asof.isoformat())
    for d in reversed(later):
        sample = load_sample(pid, d, archive)
        w = sample.weather.data if sample and sample.weather.usable else None
        if w is not None:
            return daily_series(w.dates, w.precipitation_mm, w.et0_mm)
    return None


def forecast_exceedance(ctx: ReportContext) -> ExceedanceForecast:
    crop, asof = ctx.request.crop, ctx.request.day
    soil = ctx.soil.category if ctx.soil else None
    genitive = CROP_GENITIVE[crop]
    if crop == CropGroup.INNA:
        return ExceedanceForecast(
            state="no_threshold",
            sentence="Rozporządzenie nie podaje progu suszy dla innej uprawy, więc nie liczymy szansy jego przekroczenia.",
        )
    w = ctx.data.weather.data if ctx.data.weather.usable else None
    if w is None or not w.dates:
        return _missing("nie ma danych o pogodzie dla tej działki")
    if soil is None:
        return _missing("nie znamy kategorii gleby, a próg zależy od niej")
    if not thresholded_periods(crop, soil):
        return ExceedanceForecast(
            state="no_threshold",
            sentence=f"Rozporządzenie nie podaje progu suszy dla {genitive} na glebie kategorii {soil}, więc nie liczymy szansy jego przekroczenia.",
        )
    daily = daily_series(w.dates, w.precipitation_mm, w.et0_mm)
    metrics = ctx.metrics
    in_season = date(asof.year, 3, 21) <= asof <= date(asof.year, 9, 30)

    if not in_season:
        season = asof.year if asof < date(asof.year, 3, 21) else asof.year + 1
        chance = next_season_chance(daily, crop, soil, _earlier_years(daily, season))
        if chance.n < MIN_YEARS:
            return _missing(
                f"mamy tylko {chance.n} wcześniejszych lat pogody tej działki, a potrzeba co najmniej {MIN_YEARS}"
            )
        return ExceedanceForecast(
            state="ok",
            method="historical",
            k=chance.k,
            n=chance.n,
            probability=chance.probability,
            years_used=list(chance.years),
            sentence=(
                f"Klimatologia: w {chance.k} z {chance.n} wcześniejszych lat bilans w sezonie spadł poniżej progu suszy "
                f"dla {genitive}. To częstość z minionych lat, nie prognoza sezonu {season}: jego pogody jeszcze nie znamy."
            ),
            skill_sentence=skill_sentence(metrics, "historical"),
        )

    periods = periods_after(asof, crop, soil)
    end = critical_end(crop, soil, asof.year)
    if not periods or end is None:
        return ExceedanceForecast(
            state="period_over",
            sentence=(
                f"Okres krytyczny dla {genitive} skończył się {day(end)}: w tym sezonie nie ma już okresu z progiem, "
                "więc nie liczymy szansy jego przekroczenia. Od 1 października podamy częstość z wcześniejszych lat."
            ),
        )
    years = _earlier_years(daily, asof.year)
    analog, own = in_season_chances(daily, asof, crop, soil, years, _overlay(ctx, asof))
    if analog.n < MIN_YEARS:
        return _missing(
            f"mamy tylko {analog.n} wcześniejszych lat pogody tej działki, a potrzeba co najmniej {MIN_YEARS}"
        )
    if _analog_loses(metrics):
        method, shown = "historical", own
        sentence = (
            f"W {own.k} z {own.n} wcześniejszych lat bilans spadł poniżej progu suszy dla {genitive} w okresie kończącym się "
            f"od {day(asof)} do {day(end)}. Dopełnianie przebiegami nie wygrało w walidacji z samą częstością, "
            "więc podajemy częstość."
        )
    else:
        method, shown = "analog", analog
        sentence = (
            f"W {analog.k} z {analog.n} wcześniejszych lat dalsza pogoda doprowadziła do przekroczenia progu suszy "
            f"dla {genitive} do {day(end)}. Bilans do {day(asof)} jest znany, resztę okresu dopełnia pogoda "
            f"tych samych dni z lat {analog.years[0]}–{analog.years[-1]}."
        )
    return ExceedanceForecast(
        state="ok",
        method=method,
        k=shown.k,
        n=shown.n,
        probability=shown.probability,
        sentence=sentence,
        skill_sentence=skill_sentence(metrics, method),
        what_happened=_what_happened(ctx, periods, soil, shown),
        years_used=list(shown.years),
    )
