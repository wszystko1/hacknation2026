"""The card "Gleba na tej działce": category with its meaning, texture bar, plant-available water, what it means.

A pure function of the finished report parts (no network): `build_card(soil, verdict, crop)` returns a `SoilCard`
for the "Przyczyny" tab, or None when the report has no soil at all. Texture comes from SoilGrids (0-30 cm), the
category from the IUNG map; the plant-available water (PAW) is a rough estimate and is always labelled as such.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.drought.kbw import CROP_GENITIVE
from app.fmt import dec
from app.geodata.soil import usda_texture_class
from app.models import CropGroup, SoilInfo, Verdict

DEFAULT_ROOT_CM = 60
ESTIMATE_LABEL = "szacunek orientacyjny"
METHOD_LINE = (
    "Metoda: środek przedziału dla klasy uziarnienia z tabeli 19 FAO-56 (Allen i in. 1998), "
    "razy głębokość strefy korzeniowej."
)
NO_TEXTURE = "Brak odczytu uziarnienia; kategoria z mapy IUNG."
HONESTY = (
    "Kategoria pochodzi z mapy IUNG; uziarnienie z modelu globalnego SoilGrids (siatka 250 m) i jest orientacyjne: "
    "w granicach jednej kategorii zgadza się z mapą IUNG w ok. 90% punktów."
)
NO_CATEGORY = "Brak kategorii gleby I–IV dla tej działki; karta pokazuje tylko to, co jest odczytane."

LINES = {
    "I": "gleba bardzo lekka, bardzo szybko przesycha",
    "II": "gleba lekka, szybko przesycha",
    "III": "gleba średnia, umiarkowanie trzyma wodę",
    "IV": "gleba ciężka, dobrze trzyma wodę",
}
CLASS_NAMES = {
    "sand": "piasek",
    "loamy sand": "piasek gliniasty",
    "sandy loam": "glina piaszczysta",
    "loam": "glina",
    "silt loam": "glina pylasta",
    "silt": "pył",
    "sandy clay loam": "glina piaszczysto-ilasta",
    "clay loam": "glina ilasta",
    "silty clay loam": "glina pylasto-ilasta",
    "sandy clay": "ił piaszczysty",
    "silty clay": "ił pylasty",
    "clay": "ił",
}
# plant-available water, mm per metre of soil: (low, high), FAO-56 table 19 (classes it lacks take the nearest one)
PAW_MM_PER_M = {
    "sand": (50, 110),
    "loamy sand": (60, 120),
    "sandy loam": (110, 150),
    "loam": (130, 180),
    "silt loam": (130, 190),
    "silt": (160, 200),
    "sandy clay loam": (110, 150),
    "clay loam": (130, 180),
    "silty clay loam": (130, 180),
    "sandy clay": (120, 200),
    "silty clay": (130, 180),
    "clay": (120, 200),
}
_POINTS = re.compile(r"(\d+) z (\d+) punktów")


@dataclass
class Segment:
    key: str  # sand / silt / clay (a CSS class)
    name: str
    pct: float
    x: float  # position and width in a 0-100 bar
    width: float


@dataclass
class Paw:
    mm: int
    low_mm: int
    high_mm: int
    root_cm: int
    label: str = ESTIMATE_LABEL
    method: str = METHOD_LINE


@dataclass
class SoilCard:
    category: str | None
    category_line: str  # "kategoria II: gleba lekka, szybko przesycha"
    share: str = ""  # "8 z 9 punktów działki"
    boundary: str = ""
    texture_name: str = ""  # "glina piaszczysta (klasy USDA)"
    segments: list[Segment] = field(default_factory=list)
    texture_note: str = ""  # shown instead of the bar when SoilGrids gave nothing
    paw: Paw | None = None
    reserve: str = ""
    threshold: str = ""
    advice: str = ""
    honesty: str = HONESTY
    how: str = ""  # one line for "Jak liczymy"

    @property
    def has_texture(self) -> bool:
        return bool(self.segments)


def _share(soil: SoilInfo) -> tuple[str, int, int]:
    m = _POINTS.search(soil.note or "")
    if soil.source != "iung" or not m:
        return "", 0, 0
    inside, total = int(m[1]), int(m[2])
    return f"{inside} z {total} punktów działki", inside, total


def _boundary(soil: SoilInfo, inside: int, total: int) -> str:
    other = soil.neighbour_category
    if soil.source == "iung" and total and total - inside >= 2:
        extra = f" (kategoria {other})" if other else ""
        return (
            f"Działka leży na granicy kategorii: w {total - inside} z {total} punktów mapa pokazuje "
            f"sąsiednią kategorię{extra}."
        )
    if other:
        return f"Uziarnienie leży blisko granicy z kategorią {other}."
    return ""


def _segments(sand: float, silt: float, clay: float) -> list[Segment]:
    total = sand + silt + clay
    if total <= 0:
        return []
    out, x = [], 0.0
    for key, name, pct in (("sand", "piasek", sand), ("silt", "pył", silt), ("clay", "ił", clay)):
        width = round(100 * pct / total, 2)
        out.append(Segment(key, name, round(pct), round(x, 2), width))
        x += width
    return out


def _paw(texture: str, root_cm: int = DEFAULT_ROOT_CM) -> Paw:
    low, high = PAW_MM_PER_M[texture]
    depth = root_cm / 100
    return Paw(
        mm=round((low + high) / 2 * depth), low_mm=round(low * depth), high_mm=round(high * depth), root_cm=root_cm
    )


def _reserve(paw: Paw, verdict: Verdict) -> str:
    p = verdict.period
    if p is None or p.days <= 0 or p.et0_mm <= 0:
        return ""
    daily = p.et0_mm / p.days
    days = round(paw.mm / daily)
    deficit = f"; bilans wody w tym okresie wyniósł {dec(p.kbw_mm)} mm" if p.kbw_mm < 0 else ""
    return (
        f"Gleba trzyma ok. {paw.mm} mm wody dostępnej dla roślin{deficit}. "
        f"Parowanie w tym okresie to średnio {dec(daily, 1)} mm na dobę, więc ten zapas starcza na ok. {days} dni "
        "parowania bez deszczu."
    )


def _threshold(soil: SoilInfo, verdict: Verdict, crop: CropGroup) -> str:
    if soil.category is None or verdict.threshold_mm is None:
        return ""
    what = CROP_GENITIVE.get(crop, "tej uprawy")
    return (
        f"Próg suszy z rozporządzenia dla kategorii {soil.category} i {what} wynosi {dec(verdict.threshold_mm)} mm: "
        "im lżejsza gleba, tym łatwiej go przekroczyć."
    )


def _advice(category: str | None) -> str:
    if category in ("I", "II"):
        return "Na glebach lekkich pomagają mulcz i międzyplon: ograniczają parowanie i zwiększają zapas wody w glebie."
    if category in ("III", "IV"):
        return "Gleba dobrze trzyma wodę, ale mulcz i ograniczenie uprawy nadal zmniejszają straty przez parowanie."
    return ""


def build_card(soil: SoilInfo | None, verdict: Verdict | None, crop: CropGroup) -> SoilCard | None:
    """The card, or None when there is no soil assessment. No texture: no bar, no PAW, a plain message."""
    if soil is None or (soil.category is None and soil.sand_pct is None):
        return None
    cat = soil.category
    line = f"kategoria {cat}: {LINES[cat]}" if cat else NO_CATEGORY
    share, inside, total = _share(soil)
    card = SoilCard(category=cat, category_line=line, share=share, boundary=_boundary(soil, inside, total))
    if soil.source == "doradca":
        card.share = "kategoria ustawiona przez doradcę"
    elif soil.source == "soilgrids":
        card.share = "kategoria z uziarnienia SoilGrids, bez mapy IUNG"
    if soil.sand_pct is None or soil.silt_pct is None or soil.clay_pct is None:
        card.texture_note = NO_TEXTURE
    else:
        texture = usda_texture_class(soil.sand_pct, soil.silt_pct, soil.clay_pct)
        card.texture_name = f"{CLASS_NAMES[texture]} (wg klas USDA)"
        card.segments = _segments(soil.sand_pct, soil.silt_pct, soil.clay_pct)
        card.paw = _paw(texture)
        if verdict is not None:
            card.reserve = _reserve(card.paw, verdict)
    if verdict is not None:
        card.threshold = _threshold(soil, verdict, crop)
    card.advice = _advice(cat)
    if card.paw:
        card.how = (
            f"Pojemność wodna gleby: {ESTIMATE_LABEL}, ok. {card.paw.mm} mm "
            f"(zakres {card.paw.low_mm}–{card.paw.high_mm} mm) w warstwie {card.paw.root_cm} cm. "
            "Założenie: strefa korzeniowa 60 cm dla każdej uprawy. " + METHOD_LINE
        )
    return card
