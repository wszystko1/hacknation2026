"""Chance that KBW falls below the threshold in a period ending between the analysis date and the end of
the critical period. Three approaches behind one interface: historical frequency, analog runs, GBDT."""

from __future__ import annotations

from app.context import ReportContext
from app.models import ExceedanceForecast


def forecast_exceedance(ctx: ReportContext) -> ExceedanceForecast:
    """Skeleton: a placeholder; the historical frequency and the analog runs come next."""
    return ExceedanceForecast(
        state="missing",
        sentence="Tu pojawi się szansa przekroczenia progu do końca okresu krytycznego, z jej trafnością.",
    )
