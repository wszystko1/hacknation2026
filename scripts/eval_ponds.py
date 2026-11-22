"""Basin check: does the score of a place single out BDOT10k ponds among random places of the same grid?

In three sentences (for the jury): (1) for 50 parcels with a ditch we take the real ponds from BDOT10k; (2) in each
parcel's height grid we draw a few cells inside the ponds and 25 random cells outside them (a fixed seed, so anybody gets
the same draw); (3) each cell gets the score the app uses to look for a place for water, and the AUC tells how often a
cell in a pond scores higher than a random one (0.5 = the score is no better than chance, 1.0 = always higher).

`make eval ONLY=ponds` writes into metrics.json, for the parcels of demo/data/eval/ditch_parcels.csv (height grid with
a ~300 m margin from scripts/fetch_retention_sample.py, pond outlines from scripts/fetch_ponds.py):

    retention.pond_auc_lowest  AUC of the depth below the plane that `fit_plane()` fits in a ~100 m window around the
                               place (the base of the basin place);
    retention.pond_auc_d8      AUC of the D8 upstream area of `placement` at the place;
    retention.pond_auc_ndmi    not computed here: the wet-zone evaluation writes it, and it takes part in the choice;
    retention.pond_auc         the AUC of the variant that `placement.basin_method()` picks from these values
                               (highest; a tie keeps the base, then D8);
    retention.n_ponds          ponds with at least one cell in a height grid.

AUC is the chance that a place in a pond scores higher than a random place (Mann-Whitney, ties count one half; no
scikit-learn). Per pond up to PER_POND cells are drawn; random places are drawn from the same grids with a fixed seed
and never from a pond outline. A pond is a depression in the height model (the water surface is flat or a pit), so
the AUC is optimistic, as for ditches. Without the downloaded data nothing is written and metrics.json keeps its values.
"""

from __future__ import annotations

import importlib.util
import json
import math
import random
import sys
import zlib
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
METRICS = ROOT / "metrics.json"
WINDOW_M = 100.0  # side of the window of the plane fit around a place
PER_POND = 5  # cells drawn in each pond
RANDOM_PER_GRID = 25  # random places in each grid
MIN_WINDOW_CELLS = 9  # fewer known cells in the window: the place is skipped
SEED = 20261122
VARIANTS = ("lowest", "d8", "ndmi")  # the order is the tie-break, as in placement._VARIANTS


# ---- AUC ----------------------------------------------------------------------------------------------------


def auc(positive: list[float], negative: list[float]) -> float | None:
    """P(positive > negative) + 0.5 P(equal), from ranks; None when one of the groups is empty."""
    if not positive or not negative:
        return None
    values = np.array(positive + negative, dtype=float)
    order = values.argsort(kind="stable")
    ranks = np.empty(len(values))
    sorted_v = values[order]
    i = 0
    while i < len(values):
        j = i
        while j + 1 < len(values) and sorted_v[j + 1] == sorted_v[i]:
            j += 1
        ranks[order[i : j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    n_pos, n_neg = len(positive), len(negative)
    u = ranks[:n_pos].sum() - n_pos * (n_pos + 1) / 2.0
    return float(u / (n_pos * n_neg))


def choose(scores: dict[str, float]) -> str:
    """The variant with the highest score; a tie keeps the base, then D8. Same rule as `placement.basin_method()`."""
    if "lowest" not in scores:
        return "lowest"
    best = max(scores.values())
    return next(name for name in VARIANTS if scores.get(name) == best)


# ---- scores of a place --------------------------------------------------------------------------------------


def pond_mask(grid, ponds: list[list[list[list[float]]]]) -> np.ndarray:
    """Cells of the grid whose centre lies in an outline of the ponds."""
    from rasterio.features import geometry_mask
    from rasterio.transform import from_origin

    if not ponds:
        return np.zeros((grid.rows, grid.cols), dtype=bool)
    shapes = [{"type": "Polygon", "coordinates": rings} for rings in ponds]
    transform = from_origin(grid.x0, grid.y_top, grid.step_m, grid.step_m)
    return geometry_mask(shapes, out_shape=(grid.rows, grid.cols), transform=transform, invert=True)


def depth_below_plane(grid, z: np.ndarray, row: int, col: int, window_m: float = WINDOW_M) -> float | None:
    """Depth of the cell below the plane fitted (`fit_plane`) to the window of `window_m` around it; metres."""
    from app.advice.placement import fit_plane
    from app.geodata import ElevationGrid

    if not math.isfinite(z[row, col]):
        return None
    half = max(1, round(window_m / grid.step_m / 2))
    r0, r1 = max(0, row - half), min(grid.rows, row + half + 1)
    c0, c1 = max(0, col - half), min(grid.cols, col + half + 1)
    block = z[r0:r1, c0:c1]
    if np.isfinite(block).sum() < MIN_WINDOW_CELLS:
        return None
    sub = ElevationGrid(
        crs=grid.crs,
        x0=grid.x0 + c0 * grid.step_m,
        y_top=grid.y_top - r0 * grid.step_m,
        step_m=grid.step_m,
        rows=r1 - r0,
        cols=c1 - c0,
        z=[[float(v) if math.isfinite(v) else None for v in line] for line in block],
        inside=[[1] * (c1 - c0) for _ in range(r1 - r0)],
    )
    try:
        plane = fit_plane(sub)
    except ValueError:
        return None
    x = grid.x0 + (col + 0.5) * grid.step_m
    y = grid.y_top - (row + 0.5) * grid.step_m
    return round(plane.a * x + plane.b * y + plane.c - float(z[row, col]), 6)


def cell_scores(
    grid, cells: list[tuple[int, int]], acc_ha: np.ndarray | None = None
) -> dict[str, list[float]]:
    """Scores of the cells: "lowest" (depth below the local plane) and "d8" (upstream area, ha), cells without a score left out."""
    from app.advice.placement import _build_surface

    z = np.array(grid.z, dtype=float).reshape(grid.rows, grid.cols)
    if acc_ha is None:
        acc_ha = _build_surface(grid).flow.acc_ha.reshape(grid.rows, grid.cols)
    out: dict[str, list[float]] = {"lowest": [], "d8": []}
    for r, c in cells:
        depth = depth_below_plane(grid, z, r, c)
        if depth is None:
            continue
        out["lowest"].append(depth)
        out["d8"].append(round(float(acc_ha[r, c]), 6))
    return out


def draw_cells(rng: random.Random, mask: np.ndarray, n: int) -> list[tuple[int, int]]:
    """Up to `n` cells drawn at random (without repeats) from the True cells of `mask`."""
    rows, cols = np.nonzero(mask)
    picks = rng.sample(range(len(rows)), min(n, len(rows)))
    return [(int(rows[i]), int(cols[i])) for i in picks]


def measure_ponds(samples: list[tuple], ndmi: float | None = None) -> dict[str, float | int]:
    """`samples`: (grid, ponds) per parcel, `grid` an ElevationGrid and `ponds` outlines in EPSG:2180.

    Places in ponds against random places of the same grids; shares rounded to 4 places.
    """
    pos: dict[str, list[float]] = {"lowest": [], "d8": []}
    neg: dict[str, list[float]] = {"lowest": [], "d8": []}
    from app.advice.placement import _build_surface

    n_ponds = 0
    for k, (grid, ponds) in enumerate(samples):
        if grid is None or not ponds:
            continue
        rng = random.Random(SEED + zlib.crc32(f"{k}:{grid.x0}:{grid.y_top}".encode()))
        z = np.array(grid.z, dtype=float).reshape(grid.rows, grid.cols)
        known = np.isfinite(z)
        in_ponds = pond_mask(grid, ponds)
        cells_pos: list[tuple[int, int]] = []
        for outline in ponds:  # inside every pond: up to PER_POND random cells
            one = pond_mask(grid, [outline]) & known
            if one.any():
                n_ponds += 1
                cells_pos += draw_cells(rng, one, PER_POND)
        if not cells_pos:
            continue
        cells_neg = draw_cells(rng, known & ~in_ponds, RANDOM_PER_GRID)  # outside every pond: RANDOM_PER_GRID random cells
        acc = _build_surface(grid).flow.acc_ha.reshape(grid.rows, grid.cols)
        for bucket, cells in ((pos, cells_pos), (neg, cells_neg)):
            got = cell_scores(grid, cells, acc)
            for key in bucket:
                bucket[key] += got[key]
    if n_ponds == 0:
        return {}
    scores: dict[str, float] = {}
    for key in ("lowest", "d8"):
        value = auc(pos[key], neg[key])
        if value is not None:
            scores[key] = round(value, 4)
    if "lowest" not in scores:
        return {}
    out: dict[str, float | int] = {f"retention.pond_auc_{k}": v for k, v in scores.items()}
    if ndmi is not None:
        out["retention.pond_auc_ndmi"] = ndmi
        scores["ndmi"] = ndmi
    out["retention.pond_auc"] = scores[choose(scores)]
    out["retention.n_ponds"] = n_ponds
    return out


# ---- the data -----------------------------------------------------------------------------------------------


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def previous_ndmi(path: Path = METRICS) -> float | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get("retention", {}).get("pond_auc_ndmi")
    except (OSError, ValueError, AttributeError):
        return None
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def load_samples() -> list[tuple]:
    """(grid, ponds) of each parcel that has both its terrain and its pond file; the margin grid when it exists."""
    sample = _load_script("fetch_retention_sample")
    ponds_store = _load_script("fetch_ponds")
    if not sample.CSV_PATH.is_file():
        return []
    out = []
    for row in sample.read_rows():
        loaded = sample.load_parcel(row["dzialka"])
        ponds = ponds_store.load_ponds(row["dzialka"])
        if loaded is None or ponds is None:
            continue
        terrain = loaded[1]
        out.append((terrain.catchment_grid or terrain.grid, ponds))
    return out


def run() -> dict[str, float | int]:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    return measure_ponds(load_samples(), previous_ndmi())


if __name__ == "__main__":
    print(run())
