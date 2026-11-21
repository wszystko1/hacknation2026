"""Water Law formalities for actions, read from prawo_wodne.csv (article, quote, PDF page, date checked).

A row that names a formality other than "sprawdź w Wodach Polskich" must carry the article, a verbatim quote, the
PDF page and the date it was checked; the loader refuses the file otherwise. An action without a row, or a row
that says "sprawdź w Wodach Polskich", gets that sentence and no article number: the text does not settle it.
"""

from __future__ import annotations

import csv
from datetime import date
from functools import lru_cache
from pathlib import Path

from app.models import LegalNote

CSV_PATH = Path(__file__).with_name("prawo_wodne.csv")
CHECK = "sprawdź w Wodach Polskich"
EXTRA_SEPARATOR = " | "


def _note(row: dict[str, str]) -> LegalNote:
    formality = row["formality"].strip()
    article = row["article"].strip()
    quote = row["quote"].strip()
    page = row["pdf_page"].strip()
    if formality == CHECK:
        if article:
            raise ValueError(f"{row['action_id']}: '{CHECK}' goes without an article number")
    elif not (article.startswith("art. ") and quote and page.isdigit() and int(page) > 0):
        raise ValueError(f"{row['action_id']}: a formality needs article, quote and PDF page")
    extra = [e.strip() for e in row["extra"].split(EXTRA_SEPARATOR) if e.strip()]
    return LegalNote(
        formality=formality,  # type: ignore[arg-type]
        article=article,
        quote=quote,
        pdf_page=int(page) if page else None,
        checked_on=date.fromisoformat(row["checked_on"].strip()),
        extra=extra,
    )


def load_notes(path: Path = CSV_PATH) -> dict[str, LegalNote]:
    with path.open(encoding="utf-8", newline="") as handle:
        return {row["action_id"].strip(): _note(row) for row in csv.DictReader(handle)}


@lru_cache(maxsize=1)
def _notes() -> dict[str, LegalNote]:
    return load_notes()


def legal_note(action_id: str) -> LegalNote:
    """The formality of one action; "sprawdź w Wodach Polskich" without an article when the CSV has no row for it."""
    note = _notes().get(action_id)
    return note.model_copy(deep=True) if note else LegalNote(formality=CHECK)
