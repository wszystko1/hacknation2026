"""Soil category I-IV from the texture of the topsoil (sand, silt, clay in % by weight, 0-30 cm).

The regulation (Dz.U. 2019 poz. 739, annex) assigns granulometric groups to four categories:
I: loose and weakly loamy sands; II: loamy sands (light and strong); III: light loams and silts;
IV: medium and heavy loams, silty clays, clays. SoilGrids gives three fractions, not the Polish group, so
we go through the USDA texture class (the triangle already used by the data layer) and map it to the category.
The mapping is a rule, not a measurement: the share of parcels where it agrees with the IUNG map is measured
separately (`soil.category_agreement` in metrics.json).
"""

from __future__ import annotations

from app.geodata.soil import usda_texture_class
from app.models import SOIL_CATEGORIES, SoilCategory

CATEGORY_OF_CLASS: dict[str, SoilCategory] = {
    "sand": "I",
    "loamy sand": "I",
    "sandy loam": "II",
    "loam": "III",
    "silt loam": "III",
    "silt": "III",
    "sandy clay loam": "III",
    "clay loam": "IV",
    "silty clay loam": "IV",
    "sandy clay": "IV",
    "silty clay": "IV",
    "clay": "IV",
}

# A fraction this many percentage points away is within the error we cannot rule out (250 m grid, model).
BOUNDARY_MARGIN_PCT = 5


def _category(sand: float, silt: float, clay: float) -> SoilCategory:
    return CATEGORY_OF_CLASS[usda_texture_class(sand, silt, clay)]


def category_from_texture(
    sand_pct: float, silt_pct: float, clay_pct: float
) -> tuple[SoilCategory, SoilCategory | None]:
    """(category, neighbouring category or None).

    The neighbour is set when moving sand and clay by up to BOUNDARY_MARGIN_PCT points (silt is the rest)
    changes the category: the texture lies near a class boundary, and the report then shows both results.
    Only the adjacent category is returned (I-II, II-III, III-IV), the one reached with the smallest shift.
    """
    category = _category(sand_pct, silt_pct, clay_pct)
    here = SOIL_CATEGORIES.index(category)
    for shift in range(1, BOUNDARY_MARGIN_PCT + 1):
        for d_sand in (-shift, 0, shift):
            for d_clay in (-shift, 0, shift):
                sand = sand_pct + d_sand
                clay = clay_pct + d_clay
                silt = sand_pct + silt_pct + clay_pct - sand - clay
                if min(sand, silt, clay) < 0:
                    continue
                other = SOIL_CATEGORIES.index(_category(sand, silt, clay))
                if other != here:
                    step = 1 if other > here else -1
                    return category, SOIL_CATEGORIES[here + step]
    return category, None
