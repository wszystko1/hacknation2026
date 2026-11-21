"""Section \"Gmina i trafność metody\"."""

from __future__ import annotations

from app.context import ReportContext
from app.models import Section
from app.sections import placeholder


def build(ctx: ReportContext) -> Section:
    return placeholder(
        "gmina",
        "Gmina i trafność metody",
        f"Brak: wynik SMSR dla gminy {ctx.parcel.commune} i tabela zgodności metody z SMSR, bo tabel SMSR jeszcze nie wczytujemy.",
    )
