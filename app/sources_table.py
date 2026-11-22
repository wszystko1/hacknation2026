"""Rows of "Skąd są dane" (the card on the map) and of the sources table, from the data layer's statuses.

Every row says in Polish what the source gave for this parcel, with the number. The data layer's own
descriptions are English, so the resolution and the "what it gave" text are written here.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from app.context import ReportContext
from app.fmt import dec
from app.geodata.models import SourceResult
from app.models import SourceRow

# data-layer source -> (label for the farmer, provider)
LABELS: dict[str, tuple[str, str]] = {
    "parcel": ("Obrys działki", "ULDK GUGiK"),
    "ortho": ("Zdjęcie działki", "ortofotomapa GUGiK"),
    "weather": ("Opad i parowanie", "IMGW, NASA POWER"),
    "soil": ("Uziarnienie gleby", "SoilGrids"),
    "terrain": ("Spadek terenu", "NMT GUGiK"),
    "water": ("Rowy i cieki", "BDOT10k"),
    "satellite": ("Zdjęcie satelitarne", "Sentinel-2"),
    "forecast": ("Prognoza 16 dni", "Open-Meteo"),
    "crop_hint": ("Mapa upraw JRC 2022", "JRC EUCROPMAP"),
}

# the outline's source as written in Parcel.outline_source -> provider shown in the row
OUTLINE_PROVIDERS = {"kopia lokalna": "kopia lokalna", "ULDK": "ULDK GUGiK", "EGiB WFS": "EGiB WFS GUGiK"}

# resolution of each source, in words the adviser can quote
RESOLUTIONS: dict[str, str] = {
    "parcel": "wektor ewidencji gruntów, skala działki",
    "ortho": "ortofotomapa, piksel źródłowy do 0,25 m",
    "weather": "posterunek IMGW (dane dobowe); gdzie brak, siatka NASA POWER ok. 50 km",
    "soil": "siatka 250 m, model globalny, nie polska mapa glebowo-rolnicza",
    "terrain": "numeryczny model terenu 1 m, próbki w regularnej siatce",
    "water": "BDOT10k 1:10 000, odczyt z obrazu mapy, dokładność 2–4 m",
    "satellite": "10 m (NDVI), 20 m (NDMI i maska chmur); przelot co 2–5 dni, o ile nie ma chmur",
    "forecast": "siatka 2–25 km, dane dobowe; po 7 dniach trafność maleje",
    "crop_hint": "piksel 10 m, mapa za rok 2022",
    "soil_category": "mapa podatności gleb na suszę, punkty w obrysie działki",
    "smsr": "gmina",
}

REASONS = {
    "timeout": "przekroczony limit czasu",
    "error": "usługa nie odpowiedziała",
    "skipped": "nie pobierano w tym raporcie",
}

KIND = {"ditch": "rów", "stream": "ciek", "canal": "kanał", "water_body": "zbiornik wodny"}


def _years(dates: list[str]) -> str:
    first, last = dates[0][:4], dates[-1][:4]
    return first if first == last else f"{first}–{last}"


def _km(x: float | None) -> str:
    return f"{dec(x)} km" if x is not None else "odległość nieznana"


def _gave_parcel(ctx: ReportContext, s: SourceResult) -> str:
    p = ctx.parcel
    return f"{dec(p.area_ha, 2)} ha, obręb {p.precinct}, gmina {p.commune}"


def _gave_ortho(ctx: ReportContext, s: SourceResult) -> str:
    o = s.data
    return f"zdjęcie {o.width}×{o.height} px, {dec(o.m_per_px, 2)} m na piksel"


def _gave_weather(ctx: ReportContext, s: SourceResult) -> str:
    w = s.data
    rain = (
        f"posterunek {w.precipitation_station}, {_km(w.precipitation_station_km)}"
        if w.precipitation_station
        else "siatka NASA POWER"
    )
    et0 = f"posterunek {w.et0_station}, {_km(w.et0_station_km)}" if w.et0_station else "siatka NASA POWER"
    text = f"opad {_years(w.dates)} ({rain}); parowanie ({et0})"
    if w.missing_days:
        text += f"; brakuje {w.missing_days} dni"
    if w.recent_filled_from:
        text += f"; dni od {w.recent_filled_from} z modelu (szacunek)"
    return text


def _gave_soil(ctx: ReportContext, s: SourceResult) -> str:
    d = s.data
    if not d.available or d.sand_pct is None:
        return "brak odczytu uziarnienia"
    return f"piasek {dec(d.sand_pct)}%, pył {dec(d.silt_pct)}%, ił {dec(d.clay_pct)}% (0–30 cm)"


def _gave_terrain(ctx: ReportContext, s: SourceResult) -> str:
    t = s.data
    slope = (
        f"spadek średni {dec(t.slope_mean_pct, 1)}%" if t.slope_mean_pct is not None else "spadek nieznany"
    )
    return f"{slope}, {t.samples} punktów w obrysie"


def _gave_water(ctx: ReportContext, s: SourceResult) -> str:
    w = s.data
    if w.nearest_any_m is None:
        return f"nic w promieniu {dec(w.search_m)} m"
    return f"najbliżej: {KIND.get(w.nearest_any_kind or '', 'woda')}, {dec(w.nearest_any_m, 1)} m od granicy"


def _gave_forecast(ctx: ReportContext, s: SourceResult) -> str:
    f = s.data
    return f"prognoza opadu i parowania na {f.days or len(f.dates)} dni od {_day(f.dates[0])}"


def _gave_crop_hint(ctx: ReportContext, s: SourceResult) -> str:
    h = s.data
    top = h.classes[0] if h.classes else None
    if top is None:
        return f"mapa za rok {h.map_year}: brak klasy w obrysie"
    return f"mapa za rok {h.map_year}: {top.name}, {dec(top.share * 100)}% obrysu"


def _day(iso: str) -> str:
    d = date.fromisoformat(iso[:10])
    return f"{d.day:02d}.{d.month:02d}.{d.year}"


GAVE: dict[str, Callable[[ReportContext, SourceResult], str]] = {
    "parcel": _gave_parcel,
    "ortho": _gave_ortho,
    "weather": _gave_weather,
    "soil": _gave_soil,
    "terrain": _gave_terrain,
    "water": _gave_water,
    "forecast": _gave_forecast,
    "crop_hint": _gave_crop_hint,
}


def sentinel_gave(ctx: ReportContext) -> tuple[str, str]:
    """What the Sentinel-2 row says: the scene date, the share of clear pixels and the number of comparable
    seasons, or "ocena roślin w toku" while the assessment is still running. Returns (text, reason); a reason
    means the row is a gap. The print view and the PDF carry the same state as the screen: nothing waits for history."""
    s = ctx.data.satellite
    cc = ctx.crop_condition
    if cc is not None and cc.state == "waiting":
        return "ocena roślin w toku", ""
    scene = s.data.current if s.usable and s.data else None
    if scene is None:
        return "", "nie ma czystego zdjęcia z okolic tej daty (chmury albo brak przelotu)"
    seasons = cc.n_seasons if cc is not None else 0
    return (
        f"zdjęcie z {_day(scene.date)}, czystych pikseli {dec(scene.valid_fraction * 100)}%, "
        f"porównywalnych sezonów: {seasons}",
        "",
    )


def _row(ctx: ReportContext, key: str) -> SourceRow:
    label, provider = LABELS[key]
    s: SourceResult = getattr(ctx.data, key)
    gave, reason = "", ""
    if key == "satellite":
        gave, reason = sentinel_gave(ctx)
        usable = not reason
    else:
        usable = s.usable
        if usable:
            try:
                gave = GAVE[key](ctx, s)
            except Exception:  # a source with an unexpected shape still gets its row
                gave = ""
    if usable:
        waiting = key == "satellite" and gave == "ocena roślin w toku"
        status = (
            "waiting"
            if waiting
            else "copy"
            if ctx.data_copy
            else "fallback"
            if s.status == "fallback"
            else "ok"
        )
    else:
        status = "missing"
        reason = reason or REASONS.get(s.status, "brak odpowiedzi usługi")
    if key == "parcel" and usable and s.data is not None:
        provider = OUTLINE_PROVIDERS.get(s.data.outline_source, provider)
    return SourceRow(
        key=key,
        label=label,
        provider=provider,
        gave=gave,
        status=status,  # type: ignore[arg-type]
        elapsed_s=round(s.elapsed_ms / 1000, 1),
        retrieved_at=s.retrieved_at,
        resolution=RESOLUTIONS[key],
        reason=reason,
        url=s.source_url,
    )


def _crop_map_listed(ctx: ReportContext) -> bool:
    """The crop map has a row when it was requested (a row of its own with the reason when it failed).

    A source that was not requested has no row: the card on the map is a fixed-height list over the
    photo, and a "not requested" line would cover the photo for nothing.
    """
    return ctx.data.crop_hint.status != "skipped"


def source_rows(ctx: ReportContext) -> list[SourceRow]:
    """The sources the report uses, then the ones fetched outside the data layer (soil category, SMSR).

    The seasonal forecast is not listed: no part of the report reads it.
    """
    rows = [_row(ctx, key) for key in LABELS if key != "crop_hint" or _crop_map_listed(ctx)]
    extra = [
        r.model_copy(update={"resolution": r.resolution or RESOLUTIONS.get(r.key, "")})
        for r in ctx.extra_sources
    ]
    return rows + extra
