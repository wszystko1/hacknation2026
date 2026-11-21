"""Section \"Uprawa gleby, która trzyma wodę\"."""

from __future__ import annotations

from app.context import ReportContext
from app.models import Section
from app.sections import placeholder


def build(ctx: ReportContext) -> Section:
    section = placeholder(
        "uprawa",
        "Uprawa gleby, która trzyma wodę",
        "Tu pojawią się zabiegi w uprawie z terminem do następnego okna suszy.",
    )
    section.actions = [a for a in ctx.actions if a.group == "uprawa"]
    return section
