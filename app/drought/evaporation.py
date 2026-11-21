"""Potential evapotranspiration by the Doroszewski-Górski formula, the second variant of the verdict.

The formula is the monthly one that IUNG-PIB publishes for the climatic water balance (Żyłowska, Kozyra 2023,
"Zmiany klimatycznego bilansu wodnego okresu wegetacyjnego w Polsce w latach 1971-2020", Studia i Raporty
IUNG-PIB 71(25), s. 66-67, after Doroszewski, Górski 1995):

    ETP = -89.6 + 0.0621 t^2 + 0.00448 h^1.66 + 9.1 f

with ETP the monthly potential evapotranspiration (mm), t the monthly mean air temperature at 2 m (deg C),
h the monthly sum of sunshine duration (hours) and f the length of the middle day of the month (hours).
The monitoring system itself is described in Doroszewski i in. 2012, "Podstawy Systemu Monitoringu Suszy
Rolniczej", IUNG-PIB; we did not obtain that text, and the 2019 IUNG expertise (s. 6) quotes a longer form
with humidity and wind that we do not use.

The formula is monthly, so a day gets the monthly value divided by the days of its month; the monthly mean
temperature and sunshine come from the days of the month that have data (at least `MIN_DAYS`).
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from collections.abc import Sequence
from datetime import date

import numpy as np

from app.geodata.et0 import extraterrestrial

SOURCE_NAME = "Doroszewski, Górski"
SOURCE_YEAR = 2012
SOURCE_TITLE = "Podstawy Systemu Monitoringu Suszy Rolniczej"
SOURCE_PUBLISHER = "IUNG-PIB"
# Printed form of the formula: Żyłowska, Kozyra 2023, s. 67.
FORMULA_TEXT = "ETP = −89,6 + 0,0621·t² + 0,00448·h^1,66 + 9,1·f"
MIN_DAYS = 7  # days with data a month needs to give a monthly mean


def etp_dg(t_mean_c: float, sunshine_month_h: float, day_length_h: float) -> float:
    """Monthly potential evapotranspiration (mm), Doroszewski-Górski, s. 67 of Żyłowska, Kozyra 2023."""
    return -89.6 + 0.0621 * t_mean_c**2 + 0.00448 * sunshine_month_h**1.66 + 9.1 * day_length_h


def day_length_h(year: int, month: int, latitude: float) -> float:
    """Astronomical day length (hours) of the middle day of the month."""
    mid = date(year, month, 15).timetuple().tm_yday
    _, n = extraterrestrial(np.array([float(mid)]), latitude)
    return float(n[0])


def etp_dg_daily(
    dates: Sequence[str],
    tmean_c: Sequence[float | None],
    sunshine_h: Sequence[float | None],
    latitude: float,
) -> list[float | None]:
    """Daily ETP (mm) aligned with `dates`; None for days of months without enough temperature or sunshine."""
    groups: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i, d in enumerate(dates):
        groups[(int(d[:4]), int(d[5:7]))].append(i)
    out: list[float | None] = [None] * len(dates)
    for (year, month), idx in groups.items():
        both = [(tmean_c[i], sunshine_h[i]) for i in idx if tmean_c[i] is not None and sunshine_h[i] is not None]
        if len(both) < MIN_DAYS:
            continue
        n_days = calendar.monthrange(year, month)[1]
        t = sum(b[0] for b in both) / len(both)
        h = sum(b[1] for b in both) / len(both) * n_days
        daily = max(etp_dg(t, h, day_length_h(year, month, latitude)), 0.0) / n_days
        for i in idx:
            out[i] = round(daily, 3)
    return out
