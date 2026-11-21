"""Section 8 "Źródła i ograniczenia": source, what it gave, time, duration, state; gaps stated plainly.

Also holds the adviser block of the plan section (`plan_advisor`): the method of the forecast and its measured skill.
"""

from __future__ import annotations

from app.context import ReportContext
from app.fmt import dec
from app.models import KeyValue, Section, TextPart
from app.sections import placeholder
from app.sources_table import source_rows

SOIL_SOURCE = {
    "iung": "mapa podatności gleb na suszę IUNG-PIB, odczytana w obrysie działki",
    "soilgrids": "uziarnienie z SoilGrids (model globalny), bo mapa IUNG-PIB nie dała kategorii dla tej działki",
    "doradca": "kategoria ustawiona przez doradcę",
    "brak": "",
}

NOT_COVERED = "Raport nie uwzględnia drenowania, wód gruntowych ani faktycznej daty siewu."

BRIER_EXPLAINED = "Wynik Briera to średni kwadrat błędu szansy: im bliżej zera, tym trafniejsza prognoza."
BSS_EXPLAINED = (
    "BSS porównuje wynik Briera z prognozą „zawsze częstość historyczna”: powyżej zera prognoza jest od niej lepsza."
)
METHOD_EXPLAINED = (
    "Dopełnianie przebiegami: znany bilans do dnia oceny, resztę okresu dopełnia pogoda tych samych dni "
    "kalendarza z każdego wcześniejszego roku; pierwsze 16 dni bierze się z prognozy, gdy jest."
)


def _num(x: object, digits: int = 3) -> str:
    return dec(float(x), digits) if isinstance(x, (int, float)) else ""


def _calibration(ctx: ReportContext) -> str:
    """Calibration in 10 bins from metrics.json (`forecast.calibration`: [{p, observed, n}, ...]); "" when absent."""
    bins = ctx.metrics.get("forecast.calibration")
    if not isinstance(bins, list) or not bins:
        return ""
    parts = []
    for i, b in enumerate(bins):
        if not isinstance(b, dict):
            continue
        parts.append(
            f"{i * 10}–{(i + 1) * 10}%: zaszło {_num(b.get('observed_pct', b.get('observed')), 0)}% (n={b.get('n', '?')})"
        )
    return "; ".join(parts)


def plan_advisor(ctx: ReportContext) -> list[KeyValue]:
    """The adviser block of the plan section: method, years, historical frequency, BSS with its interval,
    Brier, calibration in 10 bins. Numbers come from the forecast and from metrics.json (`forecast.*`);
    a number that is not there is named as missing, with the reason."""
    f, m = ctx.forecast, ctx.metrics
    method = {"historical": "częstość historyczna (klimatologia)", "analog": "dopełnianie przebiegami"}.get(
        f.method if f else "", ""
    )
    rows = [KeyValue(key="Metoda prognozy", value=f"{method or 'brak: prognoza nie została policzona'}. {METHOD_EXPLAINED}")]
    if f is not None and f.years_used:
        rows.append(KeyValue(key="Lata w prognozie", value=f"{len(f.years_used)} ({f.years_used[0]}–{f.years_used[-1]})"))
    if f is not None and f.k is not None and f.n:
        rows.append(KeyValue(key="Częstość historyczna", value=f"{f.k} z {f.n} wcześniejszych lat"))
    bss = m.get("forecast.brier_skill")
    if isinstance(bss, (int, float)):
        low, high = m.get("forecast.brier_skill_ci_low"), m.get("forecast.brier_skill_ci_high")
        ci = f", przedział 95%: {_num(low)} do {_num(high)}" if low is not None and high is not None else ""
        rows.append(KeyValue(key="BSS", value=f"{_num(bss)}{ci}. {BSS_EXPLAINED}"))
    else:
        rows.append(KeyValue(key="BSS", value=f"brak: pomiaru, bo metrics.json nie ma jeszcze wyniku walidacji prognozy. {BSS_EXPLAINED}"))
    brier = m.get("forecast.brier")
    if isinstance(brier, (int, float)):
        rows.append(KeyValue(key="Brier", value=f"{_num(brier)}. {BRIER_EXPLAINED}"))
    else:
        rows.append(KeyValue(key="Brier", value=f"brak: pomiaru, bo metrics.json nie ma jeszcze wyniku walidacji prognozy. {BRIER_EXPLAINED}"))
    calibration = _calibration(ctx)
    rows.append(
        KeyValue(
            key="Kalibracja (10 przedziałów)",
            value=calibration or "brak: wykresu kalibracji, bo walidacja prognozy nie zapisała przedziałów",
        )
    )
    return rows


def _sentences(ctx: ReportContext, rows: list) -> list[str]:
    out = [NOT_COVERED]
    soil = ctx.soil
    if soil is not None and soil.category is not None and SOIL_SOURCE.get(soil.source):
        out.append(f"Kategoria gleby: {SOIL_SOURCE[soil.source]}.")
    elif soil is not None:
        out.append("Brak: kategorii gleby, bo żadne źródło nie dało odczytu dla tej działki.")
    w = ctx.data.weather.data if ctx.data.weather.usable else None
    if w is not None and w.precipitation_station:
        out.append(
            f"Opad mierzył posterunek {w.precipitation_station} ({dec(w.precipitation_station_km)} km od działki); "
            f"parowanie liczono ze stacji {w.et0_station} ({dec(w.et0_station_km)} km)."
            if w.et0_station
            else f"Opad mierzył posterunek {w.precipitation_station} ({dec(w.precipitation_station_km)} km od działki)."
        )
    out += [f"Brak: {r.label[0].lower()}{r.label[1:]}, bo {r.reason}." for r in rows if r.status == "missing"]
    return out


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
            text=f"; brak: {', '.join(r.label[0].lower() + r.label[1:] for r in missing)}." if missing else ".",
            warn=bool(missing),
        ),
    ]
    section.chip = f"razem {total:.1f} s".replace(".", ",")
    section.sentences = _sentences(ctx, rows)
    section.advisor = [
        KeyValue(key=r.label, value=r.resolution)
        for r in rows
        if r.resolution
    ]
    return section
