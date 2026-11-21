"""Section \"Ostatnie 10 sezonów na tej działce\"."""

from __future__ import annotations

from app.context import ReportContext
from app.models import Section
from app.sections import placeholder


def build(ctx: ReportContext) -> Section:
    return placeholder(
        "historia",
        "Ostatnie 10 sezonów na tej działce",
        "Tu pojawi się najgorszy bilans każdego z 10 sezonów wobec progu i liczba sezonów pod progiem.",
    )
