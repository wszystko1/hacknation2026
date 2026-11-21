"""Section \"Czy nawadniać\"."""

from __future__ import annotations

from app.context import ReportContext
from app.models import Section
from app.sections import placeholder


def build(ctx: ReportContext) -> Section:
    section = placeholder(
        "nawadnianie", "Czy nawadniać", "Tu pojawi się decyzja o nawadnianiu z dawką w mm i m³ na działkę."
    )
    section.actions = [a for a in ctx.actions if a.group == "nawadnianie"]
    return section
