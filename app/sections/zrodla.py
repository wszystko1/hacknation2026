"""Section 8 "Źródła i ograniczenia": source, what it gave, time, duration, state; gaps stated plainly."""

from __future__ import annotations

from app.context import ReportContext
from app.models import Section, TextPart
from app.sections import placeholder
from app.sources_table import source_rows


def build(ctx: ReportContext) -> Section:
    section = placeholder("zrodla", "Źródła, czasy i braki danych", "")
    rows = source_rows(ctx)
    ok = [r for r in rows if r.status in ("ok", "fallback", "copy")]
    missing = [r for r in rows if r.status == "missing"]
    total = sum(r.elapsed_s or 0 for r in rows)
    section.state = "ready"
    section.reason = ""
    section.summary = [
        TextPart(text=f"{len(ok)} z {len(rows)}", bold=True),
        TextPart(text=" źródeł z danymi"),
        TextPart(
            text=f"; brak: {', '.join(r.label.lower() for r in missing)}." if missing else ".",
            warn=bool(missing),
        ),
    ]
    section.chip = f"razem {total:.1f} s".replace(".", ",")
    section.sentences = [
        "Raport nie uwzględnia drenowania, wód gruntowych ani faktycznej daty siewu.",
    ]
    return section
