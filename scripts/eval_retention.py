"""Placement check: does the outlet point land at a ditch, and does every retention action have a place or a reason.

`make eval ONLY=retention` writes into metrics.json:

(a) Ditches. For each parcel of demo/data/eval/ditch_parcels.csv (farmland parcels with a BDOT10k ditch within 50 m
    of the boundary, downloaded by scripts/fetch_retention_sample.py) the outlet point of each variant counts as a
    hit when it lies within 30 m of the ditch outline (`hit`). Shares of parcels with a hit:
    retention.outlet_hit_lowest  the lowest boundary point, `lowest_boundary_point()`;
    retention.outlet_hit_d8      the largest outlet of D8 accumulation on the margin grid, `runoff()`;
    retention.outlet_hit_random  the mean over parcels of the share of 100 random boundary points (fixed seed) that hit;
    retention.outlet_hit_ndmi    not computed here: the wet-zone evaluation writes it, and it takes part in the choice;
    retention.outlet_hit_share   the score of the variant that `placement.outlet_method()` picks from these values
                                 (highest score; a tie keeps the base, then D8);
    retention.n_ditch_parcels    parcels counted.
    A ditch is a depression in the height model, so a point that follows the terrain down ends at a ditch more often
    than it would in the field: the shares are optimistic.

(b) Places. For each parcel of demo/data/eval/parcels50.csv the report is built and its retention actions are counted:
    retention.place_or_reason_share (an action has a place on the map or the sentence "brak miejsca na działce, bo …"),
    retention.with_place_share (has a place) and retention.n_parcels (reports built).

Each part needs its data (data/raw for (a), the network or the download cache for (b)); a part without data writes
nothing and metrics.json keeps its earlier values.
"""

from __future__ import annotations

import importlib.util
import json
import math
import random
import sys
import zlib
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METRICS = ROOT / "metrics.json"
HIT_M = 30.0  # an outlet point within this distance of the ditch outline is a hit
N_RANDOM = 100  # random boundary points per parcel
SEED = 20261122
VARIANTS = ("lowest", "d8", "ndmi")  # the order is the tie-break, as in placement._VARIANTS


# ---- the hit ------------------------------------------------------------------------------------------------


def _segment_distance(px: float, py: float, a: list[float], b: list[float]) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length2 = dx * dx + dy * dy
    t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / length2))
    return math.hypot(px - (a[0] + t * dx), py - (a[1] + t * dy))


def distance_to_rings(point: list[float], rings: list[list[list[float]]]) -> float:
    """Distance in metres from the point to the nearest segment of the rings; inf when there are none."""
    best = math.inf
    for ring in rings:
        if len(ring) == 1:
            best = min(best, math.hypot(point[0] - ring[0][0], point[1] - ring[0][1]))
        for a, b in zip(ring, ring[1:], strict=False):
            best = min(best, _segment_distance(point[0], point[1], a, b))
    return best


def hit(point: list[float] | None, rings: list[list[list[float]]], max_m: float = HIT_M) -> bool:
    """True when the point (EPSG:2180 [x, y]) lies within `max_m` of a ring of the ditch outline."""
    return point is not None and distance_to_rings(point, rings) <= max_m


def ditch_rings(water) -> list[list[list[float]]]:
    return [ring for f in water.features if f.kind == "ditch" for ring in f.rings_2180]


# ---- the variants -------------------------------------------------------------------------------------------


def random_boundary_points(
    outline: list[list[float]], n: int = N_RANDOM, seed: str = ""
) -> list[list[float]]:
    """`n` points spread at random (uniformly by length) along the outline; the same seed gives the same points."""
    rng = random.Random(SEED + zlib.crc32(seed.encode()))
    lengths = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(outline, outline[1:], strict=False)]
    total = sum(lengths)
    segments = list(zip(outline, outline[1:], lengths, strict=False))
    points = []
    for _ in range(n):
        d = rng.uniform(0.0, total)
        for k, (a, b, length) in enumerate(segments):
            if d <= length or k == len(segments) - 1:  # the last segment takes what rounding leaves over
                t = 0.0 if length == 0 else min(d / length, 1.0)
                points.append([a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])])
                break
            d -= length
    return points


def outlet_points(parcel, terrain) -> dict[str, list[float] | None]:
    """The outlet point of the base ("lowest", from the 50 m grid the report uses) and of D8 (margin grid)."""
    from app.advice.placement import PlacementInput, lowest_boundary_point, runoff

    outline = parcel.rings_2180[0]
    base = PlacementInput(outline, terrain.grid, terrain.lowest_outline_point_2180)
    d8_grid = terrain.catchment_grid or terrain.grid
    flow = runoff(PlacementInput(outline, d8_grid, None))
    first = flow.outlets[0] if flow.outlets else None
    return {
        "lowest": lowest_boundary_point(base),
        "d8": [first.x_2180, first.y_2180] if first else None,
    }


def choose(scores: dict[str, float]) -> str:
    """The variant with the highest score; a tie keeps the base, then D8. Same rule as `placement.outlet_method()`."""
    if "lowest" not in scores:
        return "lowest"
    best = max(scores.values())
    return next(name for name in VARIANTS if scores.get(name) == best)


def previous_ndmi(path: Path = METRICS) -> float | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get("retention", {}).get("outlet_hit_ndmi")
    except (OSError, ValueError, AttributeError):
        return None
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def measure_ditches(samples: list[tuple], ndmi: float | None = None) -> dict[str, float | int]:
    """`samples`: (parcel, terrain, water) of each parcel with a ditch. Shares of parcels, rounded to 4 places."""
    if not samples:
        return {}
    hits = {"lowest": 0, "d8": 0}
    random_share = 0.0
    for parcel, terrain, water in samples:
        rings = ditch_rings(water)
        for name, point in outlet_points(parcel, terrain).items():
            hits[name] += hit(point, rings)
        pts = random_boundary_points(parcel.rings_2180[0], N_RANDOM, parcel.id)
        random_share += sum(hit(p, rings) for p in pts) / len(pts)
    n = len(samples)
    out: dict[str, float | int] = {
        "retention.outlet_hit_lowest": round(hits["lowest"] / n, 4),
        "retention.outlet_hit_d8": round(hits["d8"] / n, 4),
        "retention.outlet_hit_random": round(random_share / n, 4),
        "retention.n_ditch_parcels": n,
    }
    scores = {"lowest": out["retention.outlet_hit_lowest"], "d8": out["retention.outlet_hit_d8"]}
    if ndmi is not None:
        out["retention.outlet_hit_ndmi"] = ndmi
        scores["ndmi"] = ndmi
    out["retention.outlet_hit_share"] = scores[choose(scores)]
    return out


# ---- the data -----------------------------------------------------------------------------------------------


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_samples() -> list[tuple]:
    fetch = _load_script("fetch_retention_sample")
    if not fetch.CSV_PATH.is_file():
        return []
    found = (fetch.load_parcel(r["dzialka"]) for r in fetch.read_rows())
    return [s for s in found if s is not None]


def measure_places(rows: list[dict[str, str]], today: date | None = None) -> dict[str, float | int]:
    """Build the report of each row and count its retention actions with a place and with a place or a reason."""
    from app.models import CropGroup, ReportRequest
    from app.report import build_report

    ep = _load_script("eval_parcels")
    today = today or date.today()
    built = actions = with_reason = with_place = 0
    for i, row in enumerate(rows, start=1):
        pid = row["dzialka"] or ep.parcel_of_point(float(row["lon"]), float(row["lat"]))
        if not pid:
            print(f"  {i:2d}  {row['wojewodztwo']}: no parcel under the point, skipped")
            continue
        day = today if row["data"] == ep.TODAY else date.fromisoformat(row["data"])
        try:
            report = build_report(ReportRequest(parcel_id=pid, day=day, crop=CropGroup(row["uprawa"])))
        except Exception as exc:  # noqa: BLE001 - a failed report is skipped and says so
            print(f"  {i:2d}  {pid}: report failed: {type(exc).__name__}")
            continue
        built += 1
        own = [a for a in report.actions if a.group == "retencja"]
        actions += len(own)
        with_place += sum(1 for a in own if a.place is not None)
        with_reason += sum(1 for a in own if a.place is not None or a.no_place_reason)
    if not built or not actions:
        return {}
    return {
        "retention.n_parcels": built,
        "retention.place_or_reason_share": round(with_reason / actions, 4),
        "retention.with_place_share": round(with_place / actions, 4),
    }


def run() -> dict[str, float | int]:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    result = measure_ditches(load_samples(), previous_ndmi())
    ep = _load_script("eval_parcels")
    if ep.CSV_PATH.is_file():
        result |= measure_places(ep.read_rows())
    return result


if __name__ == "__main__":
    print(run())
