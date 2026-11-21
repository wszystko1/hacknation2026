"""Section \"Czy nawadniać\"."""

from __future__ import annotations

from app.context import ReportContext
from app.models import Section
from app.sections import placeholder


def build(ctx: ReportContext) -> Section:
    section = placeholder(
        "nawadnianie",
        "Czy nawadniać",
        "Brak: decyzja o nawadnianiu z dawką w mm i m³, bo reguł nawadniania jeszcze nie wczytujemy.",
    )
    section.actions = [a for a in ctx.actions if a.group == "nawadnianie"]
    return section
