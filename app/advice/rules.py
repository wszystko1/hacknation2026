"""Rules on indicators: diagnosed cause + condition -> action sentence with numbers, term, source.

Covers soil and crop management and irrigation; retention lives in app.advice.retention.
"""

from __future__ import annotations

from app.context import ReportContext
from app.models import Action


def field_actions(ctx: ReportContext) -> list[Action]:
    """Skeleton: one placeholder per group; the catalogue of 26 actions and their conditions come next."""
    if ctx.diagnosis is None or not ctx.diagnosis.causes:
        return []
    cause = ctx.diagnosis.causes[0].words
    return [
        Action(
            id="uprawa-placeholder",
            n=0,
            group="uprawa",
            title="Zabieg w uprawie",
            sentence="Tu pojawi się zabieg w uprawie z terminem, dobrany do gleby i przyczyny.",
            cause=cause,
            when="Tu pojawi się termin",
            source="Tu pojawi się źródło",
        ),
        Action(
            id="nawadnianie-placeholder",
            n=0,
            group="nawadnianie",
            title="Decyzja o nawadnianiu",
            sentence="Tu pojawi się decyzja „teraz tak / nie” z dawką w mm i m³ na działkę.",
            cause=cause,
            when="Tu pojawi się termin",
            source="Tu pojawi się źródło",
        ),
    ]
