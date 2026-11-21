"""Section \"Uprawa gleby, która trzyma wodę\"."""

from __future__ import annotations

from app.context import ReportContext
from app.models import Section
from app.sections import placeholder


def build(ctx: ReportContext) -> Section:
    section = placeholder(
        "uprawa",
        "Uprawa gleby, która trzyma wodę",
        "Brak: zabiegi w uprawie z terminem, bo katalog działań w uprawie jeszcze nie jest wczytany.",
    )
    section.actions = [a for a in ctx.actions if a.group == "uprawa"]
    return section
