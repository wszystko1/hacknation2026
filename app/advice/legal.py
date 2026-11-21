"""Water Law formalities for actions, read from prawo_wodne.csv (article, quote, PDF page, date checked)."""

from __future__ import annotations

from app.models import LegalNote


def legal_note(action_id: str) -> LegalNote:
    """Skeleton: every action says "sprawdź w Wodach Polskich" until the CSV with quotes is in place."""
    return LegalNote(formality="sprawdź w Wodach Polskich")
