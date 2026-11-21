"""Sections 1-8 of the report. Each module has `build(ctx) -> Section`; app.report calls them in order."""

from __future__ import annotations

from app.models import SECTION_ORDER, Section, SectionId, TextPart


def placeholder(section_id: SectionId, heading: str, what: str, waiting_for: str = "") -> Section:
    """A section that is not computed yet: says what will be there."""
    n, title = next((n, t) for i, n, t in SECTION_ORDER if i == section_id)
    return Section(
        id=section_id,
        n=n,
        title=title,
        heading=heading,
        state="loading" if waiting_for else "missing",
        summary=[TextPart(text=what)],
        waiting_for=waiting_for,
        reason=what,
    )
