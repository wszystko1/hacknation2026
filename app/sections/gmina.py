"""Section \"Gmina i trafność metody\"."""

from __future__ import annotations

from app.context import ReportContext
from app.models import Section
from app.sections import placeholder


def build(ctx: ReportContext) -> Section:
    return placeholder(
        "gmina",
        "Gmina i trafność metody",
        "Tu pojawi się wynik SMSR dla gminy obok wyniku działki i tabela zgodności metody z SMSR.",
    )
