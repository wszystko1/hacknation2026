"""Soil category I-IV of the drought regulation for the parcel: IUNG map layer first, SoilGrids texture second."""

from __future__ import annotations

import logging

from app.context import ReportContext
from app.models import SoilCategory, SoilInfo, SourceRow
from app.soil import iung
from app.soil.texture import category_from_texture

log = logging.getLogger(__name__)

WORDS = {
    "I": "gleba bardzo podatna na suszę (kat. I)",
    "II": "gleba podatna na suszę (kat. II)",
    "III": "gleba średnio podatna na suszę (kat. III)",
    "IV": "gleba mało podatna na suszę (kat. IV)",
}
ROW_LABEL = "Kategoria gleby"
SOILGRIDS_PROVIDER = "SoilGrids, kategoria z uziarnienia (reguła)"


def _words(category: SoilCategory, extra: str = "") -> str:
    return WORDS[category].removesuffix(")") + (f"; {extra}" if extra else "") + ")"


def _row(
    ctx: ReportContext,
    provider: str,
    status: str,
    gave: str = "",
    reason: str = "",
    url: str = "",
    retrieved_at: str = "",
) -> None:
    ctx.extra_sources.append(
        SourceRow(
            key="soil_category", label=ROW_LABEL, provider=provider, gave=gave, status=status,  # type: ignore[arg-type]
            reason=reason, url=url, retrieved_at=retrieved_at,
        )
    )  # fmt: skip


def _texture(ctx: ReportContext) -> tuple[float | None, float | None, float | None]:
    soil = ctx.data.soil.data if ctx.data.soil.usable else None
    if soil is None or soil.sand_pct is None or soil.silt_pct is None or soil.clay_pct is None:
        return None, None, None
    return soil.sand_pct, soil.silt_pct, soil.clay_pct


def _from_iung(
    ctx: ReportContext, sand: float | None, silt: float | None, clay: float | None
) -> SoilInfo | None:
    """The map reading as SoilInfo, or None when the map gives no category I-IV for the parcel."""
    rings = ctx.data.parcel.data.rings_4326
    try:
        reading, frozen = iung.read_for_parcel(ctx.parcel.id, rings)
    except Exception:  # a broken map service must not stop the report: SoilGrids is next
        log.exception("IUNG soil layer failed")
        reading, frozen = None, False
    if reading is None:
        return None
    result = iung.classify(reading)
    status = "copy" if ctx.data_copy or frozen else "ok"
    if result.category is None:
        if result.organic:
            _row(ctx, iung.PROVIDER, "missing", reason="mapa IUNG pokazuje tu gleby organiczne, bez kategorii I–IV",
                 url=reading.url)  # fmt: skip
            return SoilInfo(
                category=None, source="iung", sand_pct=sand, silt_pct=silt, clay_pct=clay,
                words="Brak: kategorii gleby I–IV, bo mapa IUNG pokazuje tu gleby organiczne, a rozporządzenie nie daje dla nich progu",
                note="gleby organiczne według mapy IUNG; kategorię może ustawić doradca",
            )  # fmt: skip
        return None
    where = f"{result.in_points} z {reading.answered} punktów działki"
    gave = f"kat. {result.category} ({where})"
    extra = ""
    if result.other:
        extra = f"część działki kat. {result.other}"
        gave += f"; część działki kat. {result.other}"
    _row(ctx, iung.PROVIDER, status, gave=gave, url=reading.url, retrieved_at=reading.retrieved_at)
    return SoilInfo(
        category=result.category, source="iung", neighbour_category=result.other,
        sand_pct=sand, silt_pct=silt, clay_pct=clay, words=_words(result.category, extra),
        note=f"odczyt mapy IUNG w {where}",
    )  # fmt: skip


def assess_soil(ctx: ReportContext) -> SoilInfo:
    """Advisor's setting, else the IUNG map reading, else the rule on SoilGrids texture, else "Brak: ..., bo ..."."""
    sand, silt, clay = _texture(ctx)
    override = ctx.request.soil_override
    if override:
        _row(ctx, "doradca", "ok", gave=f"kat. {override}")
        return SoilInfo(
            category=override, source="doradca", words=WORDS[override], note="kategoria ustawiona przez doradcę",
            sand_pct=sand, silt_pct=silt, clay_pct=clay,
        )  # fmt: skip
    from_map = _from_iung(ctx, sand, silt, clay)
    if from_map is not None:
        return from_map
    if sand is None or silt is None or clay is None:
        _row(
            ctx,
            SOILGRIDS_PROVIDER,
            "missing",
            reason="mapa IUNG i SoilGrids nie dały wartości dla tego punktu",
        )
        return SoilInfo(
            category=None, source="brak",
            words="Brak: kategorii gleby, bo mapa IUNG i SoilGrids nie dały wartości dla tego punktu",
            note="doradca może ustawić kategorię (parametr gleba)",
        )  # fmt: skip
    category, neighbour = category_from_texture(sand, silt, clay)
    texture = f"piasek {sand:.0f}%, pył {silt:.0f}%, ił {clay:.0f}%"
    extra = f"blisko granicy z kat. {neighbour}" if neighbour else ""
    gave = f"kat. {category} z uziarnienia ({texture})" + (f"; {extra}" if extra else "")
    _row(ctx, SOILGRIDS_PROVIDER, "fallback", gave=gave, reason="mapa IUNG nie dała kategorii dla działki",
         url=ctx.data.soil.source_url)  # fmt: skip
    return SoilInfo(
        category=category, source="soilgrids", neighbour_category=neighbour,
        sand_pct=sand, silt_pct=silt, clay_pct=clay, words=_words(category, extra),
        note=f"kategoria z uziarnienia SoilGrids 0–30 cm ({texture}); mapa IUNG nie dała kategorii",
    )  # fmt: skip
