"""Rules on indicators: diagnosed cause + condition -> action sentence with numbers, term, source.

Covers soil and crop management and irrigation; retention lives in app.advice.retention.
"""

from __future__ import annotations

from app.context import ReportContext
from app.models import Action


def field_actions(ctx: ReportContext) -> list[Action]:
    """No soil, crop or irrigation action until the action catalogue exists.

    Sections 5 and 7 then print their explicit "Brak: …" sentence instead of an invented action.
    """
    return []
