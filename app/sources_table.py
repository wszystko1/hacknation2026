"""Rows of "Skąd są dane" (the card on the map) and of the sources table, from the data layer's statuses."""

from __future__ import annotations

from app.context import ReportContext
from app.models import SourceRow

# data-layer source -> (label for the farmer, provider)
LABELS: dict[str, tuple[str, str]] = {
    "parcel": ("Obrys działki", "ULDK GUGiK"),
    "ortho": ("Zdjęcie działki", "ortofotomapa GUGiK"),
    "weather": ("Opad i parowanie", "Open-Meteo / IMGW"),
    "soil": ("Uziarnienie gleby", "SoilGrids"),
    "terrain": ("Spadek terenu", "NMT GUGiK"),
    "water": ("Rowy i cieki", "BDOT10k"),
    "satellite": ("Zdjęcie satelitarne", "Sentinel-2"),
    "forecast": ("Prognoza 16 dni", "Open-Meteo"),
}

REASONS = {
    "timeout": "przekroczony limit czasu",
    "error": "usługa nie odpowiedziała",
    "skipped": "nie pobierano dla tej daty",
}


def source_rows(ctx: ReportContext) -> list[SourceRow]:
    rows = []
    for key, (label, provider) in LABELS.items():
        s = getattr(ctx.data, key)
        if s.usable:
            status = "copy" if ctx.data_copy else ("fallback" if s.status == "fallback" else "ok")
            reason = ""
        else:
            status = "missing"
            reason = s.error or REASONS.get(s.status, s.status)
        rows.append(
            SourceRow(
                key=key,
                label=label,
                provider=provider,
                status=status,
                elapsed_s=round(s.elapsed_ms / 1000, 1),
                retrieved_at=s.retrieved_at,
                resolution=s.resolution,
                reason=reason,
                url=s.source_url,
            )
        )
    return rows + ctx.extra_sources
