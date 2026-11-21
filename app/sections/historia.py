"""Section \"Ostatnie 10 sezonów na tej działce\"."""

from __future__ import annotations

from app.context import ReportContext
from app.models import Section
from app.sections import placeholder


def build(ctx: ReportContext) -> Section:
    return placeholder(
        "historia",
        "Ostatnie 10 sezonów na tej działce",
        "Brak: bilans 10 ostatnich sezonów wobec progu, bo historii sezonów jeszcze nie liczymy.",
    )
