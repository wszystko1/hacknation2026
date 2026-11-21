"""Sections 1-8 of the report. Each module has `build(ctx) -> Section`; app.report calls them in order."""

from __future__ import annotations

import re

from app.models import SECTION_ORDER, Section, SectionId, TextPart

_FUTURE = re.compile(r"^Tu pojaw(?:i się|ią się)\s+", re.IGNORECASE)


def empty_sentence(what: str) -> str:
    """One sentence of the empty state: "Brak: <what> bo <why>."

    A caller that already wrote "Brak: ..." is kept as it is. A future-tense promise of X is turned
    into the missing thing ("Brak: X"), so no page ever announces something that is not there.
    """
    text = what.strip()
    if text.startswith("Brak:"):
        return text
    text = _FUTURE.sub("", text)
    return f"Brak: {text}"


def placeholder(section_id: SectionId, heading: str, what: str, waiting_for: str = "") -> Section:
    """A section without a result: the empty state of the design, one sentence "Brak: <what> bo <why>".

    Without `waiting_for` the section is `missing` and shows the sentence (the farmer view folds it into
    one row of the table of contents, the adviser view keeps it with the reason). With `waiting_for` the
    result is still being computed (`loading`).
    """
    n, title = next((n, t) for i, n, t in SECTION_ORDER if i == section_id)
    sentence = empty_sentence(what)
    return Section(
        id=section_id,
        n=n,
        title=title,
        heading=heading,
        state="loading" if waiting_for else "missing",
        summary=[] if waiting_for else [TextPart(text=sentence)],
        waiting_for=waiting_for,
        reason=sentence,
    )
