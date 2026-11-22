"""Do the cause flags "too little rain" and "high evaporation" fire in the dry periods SMSR and SPI-3 call dry?

The report names a cause when its rule holds (app/advice/diagnosis.py: rain at most 85% / evaporation at least
110% of the usual season). Nothing has checked those flags against the observed weather. For every commune,
year and one of the 14 periods of the regulation we compute the flag with the report's own functions and compare it
with two references:

- SMSR IUNG, two readings of the commune page (all crops and soil categories together): `smsr` calls the period dry
  when at least half of the "+" / "-" cells carry "+", `smsr_any` when at least one does. The first run showed that the
  strict reading leaves 1.2% dry periods, so the lenient one was added next to it; both are reported. Years 2020-2026,
  the test communes of demo/data/eval/gminy.csv.
- SPI-3: precipitation of the 91 days that end with the period, ranked against the same window in every year of the
  commune's series (empirical SPI, no gamma fit), dry when SPI <= -1. Years 2015-2025 (and 2026 where SMSR exists).

Each flag comes in two variants: the fixed threshold of the report, and a percentile one (rain below the 25th, evaporation
above the 75th percentile of the commune's earlier seasons). The numbers are a sanity check, not a calibration:
SMSR gives only seven years, so no threshold is changed on them. Writes the `causes.*` keys of metrics.json:
causes.<sample>.<flag>.<variant>.<reference>.<measure>.
"""

from __future__ import annotations

import csv
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from statistics import NormalDist

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.advice.diagnosis import (  # noqa: E402
    MIN_DATA_SHARE,
    SEASONS,
    UsualSeason,
    _evaporation_cause,
    _rain_cause,
    _usual_of,
)
from app.drought.kbw import PERIODS, period_balance, period_dates  # noqa: E402
from app.models import CropGroup, PeriodBalance  # noqa: E402
from app.smsr.parser import SmsrPageError, parse_commune_page  # noqa: E402
from app.validation.agreement import confusion, scores  # noqa: E402
from scripts.eval_smsr import COMMUNES, SMSR_DIR, WEATHER_DIR  # noqa: E402

HISTORY_DIR = ROOT / "data" / "raw" / "weather_history"
SMSR_YEARS = range(2020, 2027)
SERIES_YEARS = range(2015, 2026)
FIRST_YEAR = 2001  # the history starts here; the earlier seasons of a case are the years before it
HISTORY_LAST = date(2025, 12, 31)  # weather_history ends here; 2026 comes from the commune snapshot
RAIN_PERCENTILE = 25.0
EVAPORATION_PERCENTILE = 75.0
MIN_PERCENTILE_SEASONS = 8  # fewer earlier seasons give no percentile
SPI_DAYS = 91  # three months
SPI_DRY = -1.0  # WMO: moderately dry and drier
SMSR_DRY_SHARE = 0.5  # share of "+" cells of a commune page and period that makes the period dry
FLAGS = ("rain", "evaporation")
VARIANTS = ("fixed", "percentile")
REFERENCES = ("smsr", "smsr_any", "spi")
MEASURES = ("balanced_accuracy", "csi", "pod", "far", "base_rate")
TABLE_KEYS = ("hits", "false_alarms", "misses", "correct_negatives")

Series = tuple[list[str], list[float | None], list[float | None]]  # ISO dates, precipitation mm, ET0 mm


@dataclass
class Case:
    """One commune, year and period: the four flags (None: no earlier seasons or too little data) and the references."""

    commune: str
    year: int
    period: int
    flags: dict[tuple[str, str], bool | None]
    spi: float | None
    smsr_share: float | None = None  # share of "+" among the "+" / "-" cells of the commune page


# ---------------------------------------------------------------- weather


def merged_series(history: dict, snapshot: dict | None) -> Series:
    """History up to 2025-12-31 followed by the days of the commune snapshot after it (2026)."""
    first = date.fromisoformat(history["start"])
    dates = [(first + timedelta(i)).isoformat() for i in range(len(history["precipitation_mm"]))]
    rain, et0 = list(history["precipitation_mm"]), list(history["et0_mm"])
    if snapshot:
        start = date.fromisoformat(snapshot["start"])
        for i, (p, e) in enumerate(zip(snapshot["precipitation_mm"], snapshot["et0_mm"], strict=True)):
            day = start + timedelta(i)
            if day > HISTORY_LAST:
                dates.append(day.isoformat())
                rain.append(p)
                et0.append(e)
    return dates, rain, et0


def season_periods(series: Series, year: int) -> dict[int, PeriodBalance]:
    """The finished periods of `year` with enough days of rain and evaporation, by period number."""
    dates, rain, et0 = series
    keep = [i for i, d in enumerate(dates) if f"{year}-03-01" <= d <= f"{year}-10-31"]
    if not keep:
        return {}
    d, p, e = ([seq[i] for i in keep] for seq in (dates, rain, et0))
    out: dict[int, PeriodBalance] = {}
    for n, _, _ in PERIODS:
        pb = period_balance(d, p, e, year, n, date(year, 12, 31), CropGroup.INNA, None)
        if pb is None:
            continue
        window = (pb.end - pb.start).days + 1
        if pb.days >= MIN_DATA_SHARE * window:
            out[n] = pb
    return out


def window_rain(series: Series, year: int, n: int) -> float | None:
    """Precipitation of the SPI_DAYS days that end with period n of `year`; None with less than 90% of the days."""
    dates, rain, _ = series
    end = period_dates(year, n)[1]
    wanted = {(end - timedelta(i)).isoformat() for i in range(SPI_DAYS)}
    values = [p for d, p in zip(dates, rain, strict=True) if d in wanted and p is not None]
    return sum(values) if len(values) >= MIN_DATA_SHARE * SPI_DAYS else None


def empirical_spi(totals: dict[int, float | None]) -> dict[int, float]:
    """SPI per year from the rank of the window total among all years (Gringorten position, ties share a rank)."""
    known = {y: v for y, v in totals.items() if v is not None}
    if len(known) < MIN_PERCENTILE_SEASONS:
        return {}
    values = np.array(list(known.values()))
    out = {}
    for year, v in known.items():
        below, equal = (values < v).sum(), (values == v).sum()
        rank = below + (equal + 1) / 2
        out[year] = NormalDist().inv_cdf((rank - 0.44) / (len(values) + 0.12))
    return out


# ---------------------------------------------------------------- flags


def percentile_flags(p: PeriodBalance, earlier: Sequence[PeriodBalance]) -> tuple[bool | None, bool | None]:
    """(less rain, more evaporation) against the percentiles of the earlier seasons of the same period."""
    if len(earlier) < MIN_PERCENTILE_SEASONS:
        return None, None
    low = float(np.percentile([e.precip_mm for e in earlier], RAIN_PERCENTILE))
    high = float(np.percentile([e.et0_mm for e in earlier], EVAPORATION_PERCENTILE))
    return p.precip_mm < low, p.et0_mm > high


def fixed_flags(p: PeriodBalance, usual: UsualSeason | None) -> tuple[bool | None, bool | None]:
    """The report's own rules (`_rain_cause`, `_evaporation_cause`); None without a usual season."""
    if usual is None:
        return None, None
    return _rain_cause(p, usual) is not None, _evaporation_cause(p, usual) is not None


def commune_cases(
    teryt: str, series: Series, smsr: dict[tuple[int, int], float] | None = None, years: Sequence[int] = ()
) -> list[Case]:
    """The cases of `years` of one commune. `smsr[(year, period)]` is the page's share of "+", absent where there is none."""
    seasons = {y: season_periods(series, y) for y in range(FIRST_YEAR, max(years, default=FIRST_YEAR) + 1)}
    out: list[Case] = []
    for n, _, _ in PERIODS:
        spi = empirical_spi({y: window_rain(series, y, n) for y in seasons})
        for year in years:
            p = seasons.get(year, {}).get(n)
            if p is None:
                continue
            earlier = [(y, seasons[y][n]) for y in range(FIRST_YEAR, year) if n in seasons.get(y, {})]
            recent = [
                (y, e) for y, e in earlier if y > year - SEASONS
            ]  # the report reads the ten seasons to date
            rain_f, evap_f = fixed_flags(p, _usual_of(recent))
            rain_p, evap_p = percentile_flags(p, [e for _, e in earlier])
            flags = {
                ("rain", "fixed"): rain_f,
                ("evaporation", "fixed"): evap_f,
                ("rain", "percentile"): rain_p,
                ("evaporation", "percentile"): evap_p,
            }
            out.append(Case(teryt, year, n, flags, spi.get(year), (smsr or {}).get((year, n))))
    return out


# ---------------------------------------------------------------- SMSR


def smsr_shares(table) -> dict[int, float]:
    """Period -> share of "+" among the "+" / "-" cells of a parsed commune page; periods without such cells are absent."""
    plus: dict[int, int] = {}
    total: dict[int, int] = {}
    for (_, _, n), symbol in table.cells.items():
        if symbol in {"+", "-"}:
            total[n] = total.get(n, 0) + 1
            plus[n] = plus.get(n, 0) + (symbol == "+")
    return {n: plus[n] / total[n] for n in total}


def load_smsr(teryt: str, smsr_dir: Path = SMSR_DIR) -> dict[tuple[int, int], float]:
    out: dict[tuple[int, int], float] = {}
    for year in SMSR_YEARS:
        page = smsr_dir / f"{year}_{teryt}.html"
        if not page.is_file():
            continue
        try:
            table = parse_commune_page(page.read_text(encoding="utf-8"))
        except SmsrPageError:
            continue
        out.update({(year, n): share for n, share in smsr_shares(table).items()})
    return out


# ---------------------------------------------------------------- measures


def reference_says_dry(c: Case, reference: str) -> bool | None:
    """The reference's verdict on a case; None where the reference has no value."""
    if reference == "spi":
        return None if c.spi is None else c.spi <= SPI_DRY
    if c.smsr_share is None:
        return None
    return c.smsr_share >= SMSR_DRY_SHARE if reference == "smsr" else c.smsr_share > 0


def pairs(cases: Sequence[Case], flag: tuple[str, str], reference: str) -> list[tuple[bool, bool]]:
    """(flag, reference says dry) of the cases that have both; a case without either is left out, not counted as 0."""
    out = []
    for c in cases:
        f = c.flags.get(flag)
        ref = reference_says_dry(c, reference)
        if f is not None and ref is not None:
            out.append((f, ref))
    return out


def measures(cases: Sequence[Case], flag: tuple[str, str], reference: str, prefix: str) -> dict:
    """The 2x2 table and the scores of one flag against one reference; empty when there is no case at all."""
    observed = pairs(cases, flag, reference)
    if not observed:
        return {}
    table = confusion(observed)
    s = scores(table)
    out: dict = {f"{prefix}.{k}": getattr(table, k) for k in TABLE_KEYS}
    out[f"{prefix}.n"] = len(observed)
    out[f"{prefix}.flag_rate"] = round(sum(f for f, _ in observed) / len(observed), 4)
    for name in MEASURES:
        if s[name] is not None:  # a measure without a denominator is absent, never 0
            out[f"{prefix}.{name}"] = round(float(s[name]), 4)
    return out


def sample_keys(name: str, cases: Sequence[Case], references: Sequence[str]) -> dict:
    out: dict = {
        f"causes.{name}.n_cases": len(cases),
        f"causes.{name}.n_communes": len({c.commune for c in cases}),
    }
    for flag in FLAGS:
        for variant in VARIANTS:
            for ref in references:
                out.update(measures(cases, (flag, variant), ref, f"causes.{name}.{flag}.{variant}.{ref}"))
    return out


def spi_vs_smsr_keys(cases: Sequence[Case]) -> dict:
    """The yardstick: how well SPI-3 alone agrees with SMSR on the same cases."""
    out: dict = {}
    for ref in ("smsr", "smsr_any"):
        observed = [
            (c.spi <= SPI_DRY, reference_says_dry(c, ref))
            for c in cases
            if c.spi is not None and reference_says_dry(c, ref) is not None
        ]
        if not observed:
            continue
        table, prefix = confusion(observed), f"causes.smsr.spi_vs_{ref}"
        s = scores(table)
        out.update({f"{prefix}.{k}": getattr(table, k) for k in TABLE_KEYS})
        out.update({f"{prefix}.{k}": round(float(s[k]), 4) for k in MEASURES if s[k] is not None})
    return out


# ---------------------------------------------------------------- run


def run(
    communes_csv: Path = COMMUNES,
    history_dir: Path = HISTORY_DIR,
    weather_dir: Path = WEATHER_DIR,
    smsr_dir: Path = SMSR_DIR,
) -> dict[str, float | int]:
    if not history_dir.is_dir() or not any(history_dir.glob("*.json")):
        print("no data/raw/weather_history: run scripts/fetch_weather_history.py first")
        return {}
    with communes_csv.open(encoding="utf-8", newline="") as f:
        teryts = [r["teryt"] for r in csv.DictReader(f) if r["zbior"] == "test"]
    smsr_cases: list[Case] = []
    series_cases: list[Case] = []
    for teryt in teryts:
        path = history_dir / f"{teryt}.json"
        if not path.is_file():
            continue
        snap_path = weather_dir / f"{teryt}.json"
        snapshot = json.loads(snap_path.read_text(encoding="utf-8")) if snap_path.is_file() else None
        series = merged_series(json.loads(path.read_text(encoding="utf-8")), snapshot)
        verdicts = load_smsr(teryt, smsr_dir)
        if verdicts:
            smsr_cases += [
                c for c in commune_cases(teryt, series, verdicts, SMSR_YEARS) if c.smsr_share is not None
            ]
        series_cases += commune_cases(teryt, series, None, SERIES_YEARS)
    if not smsr_cases and not series_cases:
        return {}
    out: dict = {}
    out.update(sample_keys("smsr", smsr_cases, REFERENCES))
    out.update(spi_vs_smsr_keys(smsr_cases))
    out.update(sample_keys("series", series_cases, ("spi",)))
    out["causes.smsr_dry_share"] = SMSR_DRY_SHARE
    out["causes.spi_dry_below"] = SPI_DRY
    return out


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=1, sort_keys=True))
