"""Agreement of the soil rule with the IUNG-PIB map: `make eval ONLY=soil`.

For each point of data/raw/soil_points/points.csv (written by scripts/fetch_soil_points.py: the map category
I-IV and the SoilGrids sand, silt, clay at the same place) we apply `category_from_texture` and compare the
result with the map. Writes
  soil.n_points               points compared,
  soil.category_agreement     share with the same category (0-1),
  soil.agreement_within_one   share where the rule is at most one category away from the map,
  soil.agreement_with_neighbour  share where the map category is the rule's category or the neighbour it names
                              when the texture lies near a class boundary (the report shows both then).
Without the CSV `run()` returns nothing and metrics.json keeps its values.
"""

from __future__ import annotations

import csv
import sys
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models import SOIL_CATEGORIES  # noqa: E402
from app.soil.texture import category_from_texture  # noqa: E402

POINTS = ROOT / "data" / "raw" / "soil_points" / "points.csv"
MIN_POINTS = 50


def read_points(path: Path | None = None) -> list[dict[str, str]]:
    with (path or POINTS).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def compare(rows: Iterable[dict[str, str]]) -> dict[str, float | int]:
    """Agreement numbers for rows with iung_category, sand_pct, silt_pct, clay_pct. Empty input gives {}."""
    n = same = within_one = with_neighbour = 0
    for row in rows:
        if row["iung_category"] not in {"1", "2", "3", "4"}:  # the map's cell values 1-4 are categories I-IV
            continue
        observed = int(row["iung_category"]) - 1
        category, neighbour = category_from_texture(
            float(row["sand_pct"]), float(row["silt_pct"]), float(row["clay_pct"])
        )
        predicted = SOIL_CATEGORIES.index(category)
        n += 1
        same += predicted == observed
        within_one += abs(predicted - observed) <= 1
        with_neighbour += observed == predicted or (
            neighbour is not None and observed == SOIL_CATEGORIES.index(neighbour)
        )
    if n == 0:
        return {}
    return {
        "soil.n_points": n,
        "soil.category_agreement": round(same / n, 4),
        "soil.agreement_within_one": round(within_one / n, 4),
        "soil.agreement_with_neighbour": round(with_neighbour / n, 4),
    }


def run() -> dict[str, float | int]:
    if not POINTS.is_file():
        print(f"eval soil: {POINTS} missing; run scripts/fetch_soil_points.py first")
        return {}
    result = compare(read_points())
    if result and result["soil.n_points"] < MIN_POINTS:
        print(f"eval soil: only {result['soil.n_points']} points (aim: at least {MIN_POINTS}); fetch again")
    return result


if __name__ == "__main__":
    print(run())
