"""Chance that KBW falls below the threshold in a period ending between the analysis date and the end of
the critical period. Three approaches behind one interface: historical frequency, analog runs, GBDT."""

from __future__ import annotations

from app.context import ReportContext
from app.models import ExceedanceForecast


def forecast_exceedance(ctx: ReportContext) -> ExceedanceForecast:
    """Not built yet: the state is `missing` and the sentence says what is missing and why."""
    return ExceedanceForecast(
        state="missing",
        sentence="Brak: szansa przekroczenia progu do końca okresu krytycznego, bo prognozy z poprzednich sezonów jeszcze nie liczymy.",
    )
