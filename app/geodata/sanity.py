"""Plausibility checks of data read from outside services, before any number reaches the report.

Every check is a small typed function returning a `Check`: a level (ok / warning / invalid) and a short Polish
reason. The rules:

* A check never guesses a value. Invalid data is treated as MISSING, with the reason written out
  ("brak: spadek niewiarygodny ..."); a warning keeps the value and adds the reason to the notes.
* A check that itself fails (bad input, unexpected type) returns `invalid` with that reason, see `guarded`.
  It never raises into the report and never turns into a number.
* All thresholds live in the block of constants below, each with where it comes from:
  "przepis" (regulation / source specification), "fizyka" (physical or geographic limit) or
  "heurystyka" (our own engineering judgement, tune with evidence).

Docs: docs/notes/walidacja-danych.md.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import numpy as np

# --- Thresholds ---------------------------------------------------------------------------------------
# Slope of a single field, in percent (rise over run * 100).
SLOPE_MAX_PLAUSIBLE_PCT = (
    40.0  # heurystyka: arable land above ~22 deg is terraced or not field; 148.9 % was an artefact
)
SLOPE_MIN_PCT = 0.0  # fizyka: a mean of |gradient| cannot be negative
SLOPE_MIN_VALID_CELL_SHARE = (
    0.5  # heurystyka: slope needs 4 valid neighbours; fewer than half of the cells in the outline -> missing
)
SLOPE_PLANE_GAP_PP = 10.0  # heurystyka: mean slope this many points above the plane's slope ...
SLOPE_PLANE_GAP_RATIO = 3.0  # heurystyka: ... and this many times above it -> rough surface or noise, warning
# Elevation model.
DEM_NODATA_VALUES = (-9999.0, -32768.0, -3.4028235e38)  # przepis: nodata markers of the GUGiK / GDAL rasters
DEM_MIN_M = -5.0  # fizyka: Poland's lowest land is -1.8 m (Raczki Elblaskie)
DEM_MAX_M = 2500.0  # fizyka: Rysy 2499 m
DEM_NODATA_WARN_SHARE = 0.10  # heurystyka
DEM_NODATA_INVALID_SHARE = 0.50  # heurystyka: more than half missing, statistics would describe the gaps
DEM_RELIEF_WARN_M = 100.0  # heurystyka: difference of heights across one parcel and its 50 m margin
DEM_RELIEF_INVALID_M = 400.0  # heurystyka: no farm field has this; a hole or a wall of nodata in the grid
DEM_ZERO_SUSPECT_MIN_MEDIAN_M = (
    5.0  # heurystyka: exact 0.0 m next to land above 5 m is nodata (the service fills gaps with 0)
)
# Weather.
PRECIP_MAX_DAILY_MM = 300.0  # fizyka: Polish daily record is ~ 270 mm
ET0_MAX_DAILY_MM = 15.0  # fizyka: FAO-56 upper range for hot dry days
MISSING_SHARE_MAX = 0.10  # przepis: same as MAX_MISSING_SHARE in app/drought/kbw.py (a test keeps them equal)
# Parcel outline.
PARCEL_MIN_HA = 0.001  # heurystyka: 10 m2
PARCEL_MAX_HA = (
    2000.0  # heurystyka: no single parcel in the cadastre is larger; a decoy or a merged polygon is
)
MAX_VERTICES_SELF_INTERSECTION = 3000  # heurystyka: the O(n^2) test stays under ~50 ms
PL_2180_X = (100_000.0, 900_000.0)  # fizyka: easting of Poland in EPSG:2180 with margin
PL_2180_Y = (100_000.0, 800_000.0)  # fizyka: northing of Poland in EPSG:2180 with margin
# Soil.
SOIL_CATEGORIES = ("I", "II", "III", "IV")  # przepis: rozporzadzenie o stwierdzaniu suszy
SOIL_SOURCES = ("iung", "soilgrids", "doradca")  # origin of a category in the report
SOIL_FRACTION_SUM_TOL_PCT = 5.0  # heurystyka: sand + silt + clay should be 100 %
# Satellite.
INDEX_MIN, INDEX_MAX = -1.0, 1.0  # fizyka: range of a normalised difference
VALID_SHARE_WARN = 0.5  # heurystyka: below this the mean rests on few pixels
VALID_SHARE_INVALID = (
    0.15  # heurystyka: satellite.py drops scenes below 0.5 anyway; this is the floor for any other caller
)
# SMSR.
SMSR_SYMBOLS = frozenset({"+", "-", "x", "#", "*", "n"})  # przepis: legend of the SMSR IUNG tables


class Level(StrEnum):
    OK = "ok"
    WARNING = "warning"
    INVALID = "invalid"


@dataclass(frozen=True)
class Check:
    level: Level
    reason: str = ""  # Polish, short, "" when ok
    name: str = ""

    @property
    def usable(self) -> bool:
        """The value may be used (ok or with a warning)."""
        return self.level is not Level.INVALID

    @property
    def missing_text(self) -> str:
        """`brak: <reason>` for an invalid check, else ""."""
        return f"brak: {self.reason}" if self.level is Level.INVALID else ""

    @property
    def note(self) -> str:
        """Line for the notes of a source: `Ostrzeżenie: ...` or `brak: ...`, "" when ok."""
        if self.level is Level.WARNING:
            return f"Ostrzeżenie: {self.reason}"
        return self.missing_text


def ok(name: str = "") -> Check:
    return Check(Level.OK, "", name)


def warn(reason: str, name: str = "") -> Check:
    return Check(Level.WARNING, reason, name)


def invalid(reason: str, name: str = "") -> Check:
    return Check(Level.INVALID, reason, name)


def worst(*checks: Check) -> Check:
    """The most severe check (invalid > warning > ok); reasons of the same level are joined."""
    for level in (Level.INVALID, Level.WARNING):
        same = [c for c in checks if c.level is level]
        if same:
            return Check(level, "; ".join(dict.fromkeys(c.reason for c in same)), same[0].name)
    return ok(checks[0].name if checks else "")


def guarded(name: str, fn: Callable[..., Check], *args: Any, **kwargs: Any) -> Check:
    """Run a check; an exception inside it becomes `invalid` with the reason, never a crash or a number."""
    try:
        result = fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - the whole point: a broken check is a gap with a reason
        return invalid(f"kontrola nie powiodła się ({type(exc).__name__})", name)
    return result if result.name else Check(result.level, result.reason, name)


def _finite(value: Any) -> bool:
    return isinstance(value, int | float | np.integer | np.floating) and math.isfinite(float(value))


# --- (a) slope -----------------------------------------------------------------------------------------
def check_slope(mean_pct: float | None, max_pct: float | None = None, valid_cell_share: float = 1.0) -> Check:
    """Slope of a field in percent. Outside 0-40 % or computed on too few valid cells: invalid (missing)."""
    name = "spadek terenu"
    if mean_pct is None:
        return invalid("spadek niewiarygodny: brak wartości", name)
    if not _finite(mean_pct) or (max_pct is not None and not _finite(max_pct)):
        return invalid("spadek niewiarygodny: wartość nie jest liczbą", name)
    if valid_cell_share < SLOPE_MIN_VALID_CELL_SHARE:
        return invalid("spadek niewiarygodny: za mało komórek modelu terenu z danymi", name)
    if not SLOPE_MIN_PCT <= mean_pct <= SLOPE_MAX_PLAUSIBLE_PCT:
        return invalid(
            f"spadek poza zakresem wiarygodnym ({SLOPE_MIN_PCT:g}–{SLOPE_MAX_PLAUSIBLE_PCT:g}%)", name
        )
    return ok(name)


def plane_slope_pct(z: np.ndarray, inside: np.ndarray, step: float) -> float | None:
    """Slope of the best-fit plane through the valid cells inside the outline (percent), None when it cannot be fitted."""
    rows, cols = np.nonzero(inside & np.isfinite(z))
    if rows.size < 4:
        return None
    a = np.column_stack([cols * step, -rows * step, np.ones(rows.size)])
    coef, *_ = np.linalg.lstsq(a, z[rows, cols], rcond=None)
    return float(math.hypot(coef[0], coef[1]) * 100.0)


def check_slope_consistency(mean_pct: float | None, plane_pct: float | None) -> Check:
    """Mean of |gradient| far above the plane's slope: rough surface or noise, a warning (the value stays)."""
    name = "spójność spadku"
    if mean_pct is None or plane_pct is None:
        return ok(name)
    if mean_pct - plane_pct > SLOPE_PLANE_GAP_PP and mean_pct > SLOPE_PLANE_GAP_RATIO * max(plane_pct, 0.5):
        return warn(
            "średni spadek znacznie większy od spadku płaszczyzny: teren pofałdowany lub dane zaszumione",
            name,
        )
    return ok(name)


# --- (b) elevation model -------------------------------------------------------------------------------
def mask_nodata(z: np.ndarray) -> np.ndarray:
    """Copy of z with the nodata markers (-9999, ...) and exact 0.0 m next to higher land set to NaN.

    The GUGiK point service answers 0.0 outside its coverage: with neighbours at 260 m those cells are gaps,
    not sea level. A grid whose median is below DEM_ZERO_SUSPECT_MIN_MEDIAN_M keeps its zeros (coast, polders).
    """
    out = np.array(z, dtype="float64", copy=True)
    for marker in DEM_NODATA_VALUES:
        out[out == marker] = np.nan
    zero = out == 0.0
    if zero.any():
        rest = out[np.isfinite(out) & ~zero]
        if rest.size and float(np.median(rest)) >= DEM_ZERO_SUSPECT_MIN_MEDIAN_M:
            out[zero] = np.nan
    return out


def check_dem(z: np.ndarray, inside: np.ndarray | None = None) -> Check:
    """Elevation grid (NaN = no data): gaps, heights outside Poland's range, relief across the grid.

    With `inside` (cells within the outline) the verdict on gaps rests on those cells: a parcel at the border
    has a grid that is half gaps (the model ends at the border) and still a complete outline.
    """
    name = "numeryczny model terenu"
    arr = np.asarray(z, dtype="float64")
    if arr.size == 0:
        return invalid("model terenu bez komórek", name)
    finite = np.isfinite(arr)
    share_missing = 1.0 - float(finite.sum()) / arr.size
    if inside is not None and inside.any():
        decisive = 1.0 - float(finite[inside].sum()) / int(inside.sum())
        where = "obrysu"
    else:
        decisive, where = share_missing, "siatki"
    if decisive >= DEM_NODATA_INVALID_SHARE:
        return invalid(f"model terenu: brak danych w {decisive:.0%} komórek {where}", name)
    values = arr[finite]
    if values.min() < DEM_MIN_M or values.max() > DEM_MAX_M:
        return invalid(
            f"model terenu: wysokości poza zakresem dla Polski ({DEM_MIN_M:g}…{DEM_MAX_M:g} m)", name
        )
    relief = float(values.max() - values.min())
    if relief > DEM_RELIEF_INVALID_M:
        return invalid(
            f"model terenu: różnica wysokości {relief:.0f} m, niewiarygodna dla jednej działki", name
        )
    checks = []
    if decisive > DEM_NODATA_WARN_SHARE:
        checks.append(warn(f"model terenu: brak danych w {decisive:.0%} komórek {where}", name))
    elif share_missing > DEM_NODATA_WARN_SHARE:
        checks.append(
            warn(f"model terenu: brak danych w {share_missing:.0%} komórek siatki (poza obrysem)", name)
        )
    if relief > DEM_RELIEF_WARN_M:
        checks.append(warn(f"model terenu: różnica wysokości {relief:.0f} m w okolicy działki", name))
    return worst(*checks) if checks else ok(name)


# --- (c) weather ---------------------------------------------------------------------------------------
def _range_check(
    values: Iterable[float | None], low: float, high: float, label: str, unit: str, name: str
) -> Check:
    bad = sum(1 for v in values if v is not None and (not _finite(v) or v < low or v > high))
    if bad:
        return invalid(f"{label} poza zakresem {low:g}–{high:g} {unit} w {bad} dniach: te dni to braki", name)
    return ok(name)


def check_precipitation(values: Sequence[float | None]) -> Check:
    """Daily precipitation 0-300 mm; negative or larger values are treated as missing days."""
    return _range_check(values, 0.0, PRECIP_MAX_DAILY_MM, "opad", "mm", "opad dzienny")


def check_et0(values: Sequence[float | None]) -> Check:
    """Daily ET0 0-15 mm; negative or larger values are treated as missing days."""
    return _range_check(values, 0.0, ET0_MAX_DAILY_MM, "parowanie", "mm", "parowanie dzienne")


def clean_series(values: Sequence[float | None], low: float, high: float) -> list[float | None]:
    """The series with out-of-range values replaced by None (missing). Never fills or corrects a value."""
    return [v if v is not None and _finite(v) and low <= v <= high else None for v in values]


def check_series_gaps(missing_share: float, label: str = "okres") -> Check:
    """More than 10 % of days missing (as in the regulation's code): the period is incomplete."""
    name = "luki w serii"
    if not _finite(missing_share) or not 0.0 <= missing_share <= 1.0:
        return invalid("udział brakujących dni poza zakresem 0–1", name)
    if missing_share > MISSING_SHARE_MAX:
        return warn(
            f"{label} niekompletny: brakuje {missing_share:.0%} dni (próg {MISSING_SHARE_MAX:.0%})", name
        )
    return ok(name)


# --- (d) parcel outline --------------------------------------------------------------------------------
def check_outline(rings_2180: Sequence[Sequence[Sequence[float]]], area_ha: float | None = None) -> Check:
    """Outline: a closed ring of >= 4 finite points, non-zero area of 0.001-2000 ha, inside Poland (EPSG:2180).

    The decoy that a hostile network puts in place of ULDK is refused earlier, by app/geodata/uldk_guard.py;
    this check catches what still gets through as a geometry (empty, degenerate, far from Poland).
    """
    name = "obrys działki"
    if not rings_2180 or len(rings_2180[0]) < 4:
        return invalid("obrys działki: za mało punktów na wielokąt", name)
    ring = rings_2180[0]
    if not all(len(p) >= 2 and _finite(p[0]) and _finite(p[1]) for p in ring):
        return invalid("obrys działki: współrzędne nie są liczbami", name)
    if tuple(ring[0][:2]) != tuple(ring[-1][:2]):
        return invalid("obrys działki: wielokąt nie jest zamknięty", name)
    if not all(PL_2180_X[0] <= p[0] <= PL_2180_X[1] and PL_2180_Y[0] <= p[1] <= PL_2180_Y[1] for p in ring):
        return invalid("obrys działki: współrzędne poza granicami Polski (EPSG:2180)", name)
    shoelace = (
        abs(sum(ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1] for i in range(len(ring) - 1))) / 2
    )
    ha = shoelace / 10_000.0
    if ha <= 0.0:
        return invalid("obrys działki: pole równe zero", name)
    if area_ha is not None and not _finite(area_ha):
        return invalid("obrys działki: pole nie jest liczbą", name)
    for value in (ha,) if area_ha is None else (ha, area_ha):
        if not PARCEL_MIN_HA <= value <= PARCEL_MAX_HA:
            return invalid(f"obrys działki: pole poza zakresem {PARCEL_MIN_HA:g}–{PARCEL_MAX_HA:g} ha", name)
    return ok(name)


def _cross(o: Sequence[float], a: Sequence[float], b: Sequence[float]) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _segments_cross(
    p1: Sequence[float], p2: Sequence[float], p3: Sequence[float], p4: Sequence[float]
) -> bool:
    """Proper crossing of two segments (touching ends do not count)."""
    d1, d2, d3, d4 = _cross(p3, p4, p1), _cross(p3, p4, p2), _cross(p1, p2, p3), _cross(p1, p2, p4)
    return d1 * d2 < 0 and d3 * d4 < 0


def check_polygon_valid(rings_2180: Sequence[Sequence[Sequence[float]]]) -> Check:
    """Self-intersecting outer ring (a bow-tie) is a warning: the area and the masks may be off. No dependencies."""
    name = "obrys działki"
    ring = rings_2180[0]
    n = len(ring) - 1
    if n < 3 or n > MAX_VERTICES_SELF_INTERSECTION:
        return ok(name)  # too short to cross itself, or too long to test in the request path
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue  # neighbours through the closing vertex
            if _segments_cross(ring[i], ring[i + 1], ring[j], ring[j + 1]):
                return warn("obrys działki ma samoprzecięcia", name)
    return ok(name)


# --- (e) soil ------------------------------------------------------------------------------------------
def check_soil_category(category: str | None, source: str) -> Check:
    """Category I-IV and a known source. "brak" with no category is fine here (the report says why elsewhere)."""
    name = "kategoria gleby"
    if category is None:
        return (
            ok(name)
            if source == "brak"
            else invalid("kategoria gleby: brak wartości przy znanym źródle", name)
        )
    if category not in SOIL_CATEGORIES:
        return invalid("kategoria gleby poza zbiorem I–IV", name)
    if source not in SOIL_SOURCES:
        return invalid("kategoria gleby: nieznane źródło (oczekiwano IUNG, SoilGrids lub doradcy)", name)
    return ok(name)


def check_soil_texture(sand: float | None, silt: float | None, clay: float | None) -> Check:
    """Fractions 0-100 % that add up to about 100 %."""
    name = "uziarnienie gleby"
    parts = (sand, silt, clay)
    if any(p is None for p in parts):
        return invalid("uziarnienie: brak frakcji", name)
    if not all(_finite(p) and 0.0 <= p <= 100.0 for p in parts):  # type: ignore[operator]
        return invalid("uziarnienie: frakcja poza zakresem 0–100%", name)
    if abs(sum(parts) - 100.0) > SOIL_FRACTION_SUM_TOL_PCT:  # type: ignore[arg-type]
        return invalid("uziarnienie: frakcje nie sumują się do 100%", name)
    return ok(name)


# --- (f) satellite -------------------------------------------------------------------------------------
def check_indices(ndvi: float | None, ndmi: float | None, valid_fraction: float) -> Check:
    """NDVI and NDMI in [-1, 1] (a value outside is invalid); share of clear pixels low -> warning, very low -> invalid."""
    name = "indeksy satelitarne"
    for label, value in (("NDVI", ndvi), ("NDMI", ndmi)):
        if value is not None and (not _finite(value) or not INDEX_MIN <= value <= INDEX_MAX):
            return invalid(f"{label} poza zakresem −1…1", name)
    if not _finite(valid_fraction) or not 0.0 <= valid_fraction <= 1.0:
        return invalid("udział czystych pikseli poza zakresem 0–1", name)
    if valid_fraction < VALID_SHARE_INVALID:
        return invalid(f"tylko {valid_fraction:.0%} czystych pikseli (chmury, cień)", name)
    if valid_fraction < VALID_SHARE_WARN:
        return warn(f"tylko {valid_fraction:.0%} czystych pikseli działki", name)
    return ok(name)


# --- (g) SMSR ------------------------------------------------------------------------------------------
def check_smsr_symbol(symbol: str | None) -> Check:
    """SMSR cell symbol from the set + - x # * n."""
    name = "symbol SMSR"
    if symbol is None:
        return invalid("symbol SMSR: brak komórki w tabeli", name)
    if symbol not in SMSR_SYMBOLS:
        return invalid(f"symbol SMSR „{symbol}” spoza oczekiwanego zbioru", name)
    return ok(name)
