"""Section 4 "Gdzie zatrzymać wodę na działce": places on the photo, terrain profile, actions with formalities."""

from __future__ import annotations

from app.context import ReportContext
from app.models import Section, TextPart
from app.sections import placeholder


def build(ctx: ReportContext) -> Section:
    section = placeholder(
        "retencja",
        "Gdzie zatrzymać wodę na działce",
        "Tu pojawi się zbliżenie działki z miejscami działań, profil terenu i formalność z Prawa wodnego.",
    )
    section.actions = [a for a in ctx.actions if a.group == "retencja"]
    placed = [a for a in section.actions if a.place]
    if placed:
        section.summary = [
            TextPart(text="Działanie nr 1: "),
            TextPart(text=placed[0].title.lower(), bold=True),
            TextPart(text=f" ({placed[0].place.description})."),
        ]
    return section
