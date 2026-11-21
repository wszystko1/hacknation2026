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
def _cells() -> dict[tuple[str, str, int], str]:
    with CSV_PATH.open(encoding="utf-8", newline="") as f:
        return {
            (row["crop"], row["soil_category"], int(row["period"])): row["threshold_mm"].strip()
            for row in csv.DictReader(f)
        }


@cache
def _table() -> dict[tuple[str, str, int], float | None]:
    return {k: (float(v) if v not in {"-", "x", ""} else None) for k, v in _cells().items()}


def threshold_cell(crop: CropGroup, soil: SoilCategory, period: int) -> str:
    """The cell as printed in the regulation: "-125", "x" (no yield loss in this period),
    "-" (crop not recommended on this soil); "" for "Inna uprawa"."""
    if crop == CropGroup.INNA:
        return ""
    return _cells().get((crop.value, soil, period), "")


def threshold_mm(crop: CropGroup, soil: SoilCategory, period: int) -> float | None:
    """Threshold in mm (negative), or None when the regulation gives none (or the crop is "Inna uprawa")."""
    if crop == CropGroup.INNA:
        return None
    return _table().get((crop.value, soil, period))
