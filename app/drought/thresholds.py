"""KBW thresholds of Dz.U. 2019 poz. 739 (annex): crop group x soil category x period -> mm.

The table lives in progi_dz_u_2019_739.csv (columns: crop = CropGroup code, soil_category = I..IV,
period = 1..14, threshold_mm = number, or "-" / "x" where the regulation gives no threshold).
"""

from __future__ import annotations

import csv
from functools import cache
from pathlib import Path

from app.models import CropGroup, SoilCategory

CSV_PATH = Path(__file__).with_name("progi_dz_u_2019_739.csv")


@cache
def _table() -> dict[tuple[str, str, int], float | None]:
    table: dict[tuple[str, str, int], float | None] = {}
    with CSV_PATH.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            value = row["threshold_mm"].strip()
            number = float(value) if value not in {"-", "x", ""} else None
            table[(row["crop"], row["soil_category"], int(row["period"]))] = number
    return table


def threshold_mm(crop: CropGroup, soil: SoilCategory, period: int) -> float | None:
    """Threshold in mm (negative), or None when the regulation gives none (or the crop is "Inna uprawa")."""
    if crop == CropGroup.INNA:
        return None
    return _table().get((crop.value, soil, period))
