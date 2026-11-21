"""Section 6 "Plan działań i termin": timeline to the next drought window, "W planie" switches, forecast."""

from __future__ import annotations

from app.context import ReportContext
from app.models import Section, TextPart
from app.sections import placeholder


def build(ctx: ReportContext) -> Section:
    section = placeholder(
        "plan",
        "Plan działań i termin",
        "Brak: oś czasu do następnego okna suszy, bo terminów działań jeszcze nie wyliczamy.",
    )
    planned = sum(1 for a in ctx.actions if a.in_plan)
    section.summary = [
        TextPart(text=f"{planned} z {len(ctx.actions)}", bold=True),
        TextPart(text=" działań w planie; oś czasu do następnego okna suszy."),
    ]
    return section
