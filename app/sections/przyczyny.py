"""Section \"Skąd ten bilans\"."""

from __future__ import annotations

from app.context import ReportContext
from app.models import Section
from app.sections import placeholder


def build(ctx: ReportContext) -> Section:
    return placeholder(
        "przyczyny",
        "Skąd ten bilans",
        "Tu pojawi się rozkład niedoboru: zwykły bilans, mniej opadu, więcej parowania, gleba i spadek terenu.",
    )
