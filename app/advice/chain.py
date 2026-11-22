"""The chain from cause to action for retention: need, opportunity, candidate, validation, action.

For every mechanism that has a retention row in the catalogue:

1. need: in the season one of the mechanism's `need_required` causes is diagnosed; off season this is waived;
2. opportunity: the terrain offers what the mechanism asks for (slope, a depression, a ditch, ...);
3. candidate: the detector of the mechanism returns a place (a geometry) or the reason there is none;
4. validation: risks are appended and the confidence drops one step;
5. action: the catalogue row that fits the parcel gives the title, the term, the formality and the sentence; the
   numbers of this parcel replace the `{...}` fields of the sentence.

The sentences live in `catalog_retencja.csv`; nothing here writes or glues a sentence. When a sentence needs a number
that this parcel does not have (no catchment on flat land, no length without a geometry), the action stays and says
the reason "brak miejsca na działce, bo …" instead. At most three actions come out, the ones that answer more
diagnosed causes first. Effects are shown only as the literature range of the row, never as millimetres of runoff.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import date
from string import Formatter

from app.advice import detectors
from app.advice import placement as pl
from app.advice.catalog import CatalogRow, effect_text, load_catalog
from app.advice.legal import legal_note
from app.advice.mechanisms import Mechanism, has_opportunity, is_needed, load_mechanisms
from app.advice.terrain_model import TerrainModel
from app.advice.validate import validate
from app.fmt import day as fmt_day
from app.fmt import dec
from app.models import NO_PLACE_PREFIX, Action, Candidate, Cause, Place

MAX_ACTIONS = 3
DORMANT_DEADLINE = (3, 20)  # earthworks are done in the dormant season: the day before 21.III
SEASON_START = (3, 21)

# The data has no sign of an existing weir or of a pond that needs protecting, so those rows are never picked.
UNKNOWABLE_ROWS = frozenset({"zastawka-istniejaca", "ochrona-zbiornika"})
# Two rows of the strip mechanism: one for a strip along a ditch, one for a strip by the lower boundary segment.
STRIP_ALONG_DITCH = "pas-buforowy-wzdluz-rowu"
STRIP_BY_BOUNDARY = "pas-trawy-przy-wyplywie"

PLACE_KIND = {
    "strip": "pas trawy",
    "balk": "miedza w poprzek stoku",
    "contour": "uprawa w poprzek stoku",
    "basin": "niecka",
}
NO_SPOT_DITCH = "rowie przy działce"
NO_SPOT = "miejscu do wskazania w terenie"
MAX_WEIRS = 5  # team proposal: more steps than this along one ditch is a ditch rebuild, not a weir
MIN_BOUNDARY_CHECK = ("basin",)  # places that stand inside the parcel: the distance to its boundary is checked


# ---------------------------------------------------------------- terrain facts


def plane_of(inp: pl.PlacementInput) -> pl.Plane | None:
    if inp.grid is None:
        return None
    try:
        return pl.fit_plane(inp.grid)
    except ValueError:
        return None


def terrain_inputs(model: TerrainModel, plane: pl.Plane | None) -> dict[str, bool]:
    """What the terrain offers, by the names in `mechanisms.csv` (`terrain_input`)."""
    depth_min = pl._cond("niecka-przy-wyplywie", "depression_min_m") or 0.2
    return {
        "spadek": plane is not None and plane.slope_pct >= detectors._flat_pct(),
        "zlewnia": model.catchment_ha is not None,
        "zagłębienie": any(d.depth_m >= depth_min - 1e-9 for d in model.depressions)
        or model.lowest_interior_2180 is not None,
        "rów": model.ditch_distance_m is not None,
    }


def _distance_to_ring(point: tuple[float, float], ring: list[list[float]]) -> float:
    best = math.inf
    for (x1, y1), (x2, y2) in zip(ring, ring[1:], strict=False):
        dx, dy = x2 - x1, y2 - y1
        length2 = dx * dx + dy * dy
        t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((point[0] - x1) * dx + (point[1] - y1) * dy) / length2))
        best = min(best, math.hypot(point[0] - x1 - t * dx, point[1] - y1 - t * dy))
    return best


# ---------------------------------------------------------------- the place of a candidate


def _anchor(candidate: Candidate) -> tuple[float, float] | None:
    """The point that carries the pin: the lowest point of a basin, the middle of a line, the centre of a polygon."""
    g = candidate.geometry
    if g is None:
        return None
    ev = candidate.evidence
    if isinstance(ev.get("lowest_x"), (int, float)) and isinstance(ev.get("lowest_y"), (int, float)):
        return float(ev["lowest_x"]), float(ev["lowest_y"])
    pts = g.coordinates
    if g.type == "point":
        return pts[0]
    if g.type == "line":
        if len(pts) == 2:
            return (pts[0][0] + pts[1][0]) / 2, (pts[0][1] + pts[1][1]) / 2
        return pts[len(pts) // 2]
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def _place(candidate: Candidate, kind: str, model: TerrainModel, ring: list[list[float]]) -> Place | None:
    anchor = _anchor(candidate)
    if anchor is None or candidate.geometry is None:
        return None
    g = candidate.geometry
    azimuth = g.azimuth_deg if kind == PLACE_KIND["contour"] else None
    return pl._place(
        kind,
        anchor[0],
        anchor[1],
        pl._where(anchor[0], anchor[1], ring),
        catchment_ha=model.catchment_ha if kind in (PLACE_KIND["strip"], PLACE_KIND["basin"]) else None,
        length_m=g.length_m,
        direction_deg=None if azimuth is None else azimuth % 180.0,
    )


# ---------------------------------------------------------------- the catalogue row for a candidate


def _fits(row: CatalogRow, mechanism: Mechanism, candidate: Candidate, slope: float | None, model: TerrainModel) -> bool:
    if row.action_id in UNKNOWABLE_ROWS:
        return False
    lo, hi = row.cond("slope_min_pct"), row.cond("slope_max_pct")
    if (lo is not None or hi is not None) and slope is None:
        return False
    if lo is not None and slope is not None and slope < lo:
        return False
    if hi is not None and slope is not None and slope > hi:
        return False
    if mechanism.detector == "no_place" and mechanism.terrain_input == "rów":
        reach = row.cond("ditch_max_m")
        if reach is not None and (model.ditch_distance_m is None or model.ditch_distance_m > reach):
            return False
    if mechanism.detector == "strip":
        along = bool(candidate.evidence.get("along_ditch"))
        if row.action_id == STRIP_ALONG_DITCH and not along:
            return False
        if row.action_id == STRIP_BY_BOUNDARY and along:
            return False
    return True


def _weirs(model: TerrainModel, plane: pl.Plane | None, inp: pl.PlacementInput, head_m: float | None) -> int | None:
    """Weirs along the fall over the parcel, one per `head_m` of drop (catalogue); None without a slope."""
    if plane is None or not head_m:
        return None
    xs = [p[0] for p in inp.outline_2180]
    ys = [p[1] for p in inp.outline_2180]
    rad = math.radians(plane.downhill_deg)
    ux, uy = math.sin(rad), math.cos(rad)
    along = [x * ux + y * uy for x, y in zip(xs, ys, strict=True)]
    drop = plane.slope_pct / 100.0 * (max(along) - min(along))
    return min(MAX_WEIRS, max(1, round(drop / head_m)))


def _fields(
    row: CatalogRow,
    candidate: Candidate,
    place: Place | None,
    model: TerrainModel,
    plane: pl.Plane | None,
    inp: pl.PlacementInput,
    area_ha: float,
) -> dict[str, str]:
    """The numbers of this parcel by field name; a field the parcel cannot fill is left out."""
    ev = candidate.evidence
    out: dict[str, str] = {"area_ha": dec(area_ha, 2)}
    out["place"] = place.description if place else (NO_SPOT_DITCH if row.mechanism == "dam_in_ditch" else NO_SPOT)
    if plane is not None:
        out["slope_pct"] = pl._slope_text(plane.slope_pct)
    if model.catchment_ha is not None:
        out["catchment_ha"] = dec(model.catchment_ha, 1)
    length = candidate.geometry.length_m if candidate.geometry else None
    if length is not None:
        out["length_m"] = dec(length, 0)
    if model.ditch_distance_m is not None:
        out["distance_m"] = dec(model.ditch_distance_m, 0)
    weirs = _weirs(model, plane, inp, row.cond("head_m"))
    if weirs is not None:
        out["n_weirs"] = str(weirs)
    words = ev.get("rows_words")
    if isinstance(words, str):
        out["rows_words"] = out["direction"] = out["kierunek"] = words
    depth = ev.get("depth_m")
    if isinstance(depth, (int, float)):
        out["depth_m"] = dec(float(depth), 1)
    out["term"] = row.term
    return out


def _fill(template: str, fields: Mapping[str, str]) -> str | None:
    """The template with its fields filled; None when a field is missing."""
    names = {name for _, name, _, _ in Formatter().parse(template) if name}
    if not names <= set(fields):
        return None
    return template.format_map(fields)


# ---------------------------------------------------------------- the action


def _source(row: CatalogRow) -> str:
    doc = row.source_doc.split(",")[0].split(";")[0].strip()
    if "zespołu" in doc.lower():
        doc = "wartość orientacyjna"
    parts = [doc] if doc else []
    if row.source_page:
        parts.append(f"s. {row.source_page}")
    if row.confidence not in doc:
        parts.append(row.confidence)
    return " · ".join(parts)


def _due(day: date, in_season: bool) -> date | None:
    if in_season:
        return None
    return date(day.year + 1 if day.month >= 10 else day.year, *DORMANT_DEADLINE)


def _candidate(
    mechanism: Mechanism,
    base: Candidate,
    row: CatalogRow,
    model: TerrainModel,
    inp: pl.PlacementInput,
    codes: list[str],
    area_ha: float,
) -> Candidate:
    cand = base.model_copy(deep=True)
    cand.action_id = row.action_id
    cand.cause_codes = list(codes)  # type: ignore[arg-type]
    cand.evidence = {**cand.evidence, "dzialka_ha": area_ha}
    if model.catchment_ha is not None:
        cand.evidence["zlewnia_ha"] = model.catchment_ha
    if model.catchment_truncated is not None:
        cand.evidence["zlewnia_ucieta"] = model.catchment_truncated
    anchor = _anchor(cand)
    if anchor is not None and mechanism.detector in MIN_BOUNDARY_CHECK:
        cand.evidence["odleglosc_od_granicy_m"] = round(_distance_to_ring(anchor, inp.outline_2180), 1)
    if row.legal_article:
        cand.legal = legal_note(row.action_id)
    return validate(cand, model)


def build_chain(
    causes: list[Cause],
    day: date,
    in_season: bool,
    model: TerrainModel,
    inp: pl.PlacementInput,
    area_ha: float,
) -> list[Action]:
    """The retention actions of the parcel, at most three, the ones that answer more causes first."""
    diagnosed = {c.code: c for c in causes}
    if not diagnosed:
        return []
    plane = plane_of(inp)
    slope = plane.slope_pct if plane else None
    offered = terrain_inputs(model, plane)
    mechanisms = load_mechanisms()
    rows_of: dict[str, list[CatalogRow]] = {}
    for row in load_catalog().values():
        if row.group == "retencja":
            rows_of.setdefault(row.mechanism, []).append(row)

    found: list[Action] = []
    for mechanism in mechanisms.values():
        rows = rows_of.get(mechanism.id)
        if not rows or not is_needed(mechanism, set(diagnosed), in_season):
            continue
        if not has_opportunity(mechanism, offered):
            continue
        base = detectors.detect(mechanism, model, inp)
        for row in rows:
            codes = [c for c in row.causes if c in diagnosed]
            if not codes:
                continue
            cand = _candidate(mechanism, base, row, model, inp, codes, area_ha)
            if not _fits(row, mechanism, cand, slope, model):
                continue
            kind = PLACE_KIND.get(mechanism.detector, "")
            place = _place(cand, kind, model, inp.outline_2180) if kind else None
            sentence = _fill(row.sentence, _fields(row, cand, place, model, plane, inp, area_ha))
            reason = "" if place else cand.no_place_reason
            if sentence is None:
                if place is not None:
                    continue  # a place without the numbers of its sentence: nothing honest to say
                sentence = reason[:1].upper() + reason[1:]
            due = _due(day, in_season)
            found.append(
                Action(
                    id=row.action_id,
                    n=0,
                    group="retencja",
                    title=row.title,
                    sentence=sentence,
                    cause=diagnosed[codes[0]].words,
                    cause_codes=codes,  # type: ignore[arg-type]
                    candidate=cand,
                    causes=[diagnosed[c].words for c in codes],
                    effect=effect_text(row),
                    when=f"{row.term}, do {fmt_day(due)}" if due else row.term,
                    due=due,
                    source=_source(row),
                    legal=cand.legal,
                    place=place,
                    no_place_reason=reason if reason.startswith(NO_PLACE_PREFIX) else "",
                )
            )
            break  # one action per mechanism: the first row that fits
    alone = {r.action_id: r.farmer_alone for r in load_catalog().values()}
    found.sort(key=lambda a: (-len(a.cause_codes), a.place is None, not alone.get(a.id, False)))
    return found[:MAX_ACTIONS]
