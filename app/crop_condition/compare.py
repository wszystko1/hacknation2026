"""Plants on the parcel against earlier seasons of the same rotation group, at the same growth phase."""

from __future__ import annotations

from datetime import date, timedelta
from statistics import median

from app.geodata import SceneIndex
from app.models import CropCondition, CropGroup, SeasonGroup

from .rotation import (
    Point,
    after_harvest,
    classify_points,
    green_up,
    usable_points,
)

MIN_SEASONS = 3  # comparable seasons needed for a statement
STALE_DAYS = 30  # the last clear reading must be at most this old on the day of the report
MAX_GAP_DAYS = 20  # two readings further apart than this are not interpolated
NDVI_MARGIN = 0.10  # team proposal: smaller differences are within what one scene can show
NDMI_MARGIN = 0.10  # team proposal
SPREAD_FACTOR = 1.5  # the margin is at least this many median absolute deviations of the earlier seasons
CLOSED_CANOPY_NDVI = 0.6  # team proposal: below it soil shows through and leaf moisture is not read
MIN_START = (6, 1)  # a bare parcel before this date has not started yet, which is not a gap of data


def _at(points: list[Point], day: date) -> Point | None:
    """The curve at `day`: a reading, or a linear mix of the two around it (None across a long gap)."""
    for a, b in zip(points, points[1:], strict=False):
        if a.day <= day <= b.day and (b.day - a.day).days <= MAX_GAP_DAYS:
            if a.day == b.day:
                return a
            w = (day - a.day).days / (b.day - a.day).days
            ndmi = None if a.ndmi is None or b.ndmi is None else a.ndmi + w * (b.ndmi - a.ndmi)
            return Point(day, a.ndvi + w * (b.ndvi - a.ndvi), ndmi, a.scene)
    if len(points) == 1 and points[0].day == day:
        return points[0]
    return None


def _peak_until(points: list[Point], day: date) -> float | None:
    """Highest NDVI up to `day`; None when the curve does not reach that day."""
    if not points or points[-1].day < day - timedelta(days=MAX_GAP_DAYS):
        return None
    return max(p.ndvi for p in points if p.day <= day)


CLOUDY = "zbyt wiele chmur na zdjęciach z tego okresu"
WINDOW_DAYS = 20  # scenes this close to the day of the report compete for the assessment


def choose_scene(points: list[Point], day: date) -> list[Point]:
    """The curve cut at the scene to assess: the largest clear share within WINDOW_DAYS before `day`.

    Ties go to the nearest scene. The curve keeps everything before the chosen scene, so the rotation group and
    the phase of growth are read as before.
    """
    near = [i for i, p in enumerate(points) if (day - p.day).days <= WINDOW_DAYS]
    if not near:
        return points
    best = max(near, key=lambda i: (points[i].scene.valid_fraction, i))
    return points[: best + 1]


def _only_cloudy(readings: list[SceneIndex], day: date) -> bool:
    """Scenes exist near `day`, but none has enough clear pixels."""
    return any(
        r.ndvi is not None and abs((date.fromisoformat(r.date) - day).days) <= WINDOW_DAYS for r in readings
    )


def _gap(why: str, **fields: object) -> CropCondition:
    return CropCondition(
        state="missing",
        words=f"Brak: stanu roślin ze zdjęć satelitarnych, bo {why}",
        reason=why,
        **fields,  # type: ignore[arg-type]
    )


def _margin(values: list[float], floor: float) -> float:
    centre = median(values)
    return max(floor, SPREAD_FACTOR * median(abs(v - centre) for v in values))


def compare(
    current: list[SceneIndex], history: dict[int, list[SceneIndex]], crop: CropGroup, day: date
) -> CropCondition:
    """Plants on `day` against earlier seasons of the same group at the same phase of growth.

    `current` holds the readings of this season; `history` the whole seasons of earlier years by year.
    The group comes from the curve of the season, not from `crop`: the parcel is compared with what grew on it.
    A season counts only when its curve is of the same group and has a reading at the same phase.
    Phase is the number of days since the start of vegetation, so a crop sown two weeks earlier is compared
    with the earlier seasons at the same stage and not on the same date. Grassland is compared by the highest
    greenness so far, because cuts fall on different dates.
    A picture right after a sharp fall of NDVI is a harvest or a cut: it says so and gives no signal.
    """
    points = [p for p in usable_points(current) if p.day.year == day.year and p.day <= day]
    if not points:
        if _only_cloudy(current, day):
            return _gap(CLOUDY)
        return _gap("nie ma czystego zdjęcia tej działki z tego sezonu (chmury albo brak zdjęć)")
    points = choose_scene(points, day)
    last = points[-1]
    seen = {"scene_date": last.day, "ndvi": round(last.ndvi, 3)}
    age = (day - last.day).days
    if age > STALE_DAYS:
        return _gap(
            f"ostatnie czyste zdjęcie ma {age} dni, a ocena wymaga zdjęcia z ostatnich {STALE_DAYS} dni",
            **seen,
        )
    group = classify_points(points)
    if group is None:
        return _gap(
            f"z tego sezonu są {len(points)} czyste zdjęcia, a do rozpoznania uprawy trzeba co najmniej 4",
            **seen,
        )
    seen["season_group"] = group
    if group == "gola_gleba":
        if (last.day.month, last.day.day) < MIN_START:
            return _gap("wegetacja na działce jeszcze nie ruszyła, więc nie ma czego porównywać", **seen)
        return _gap(f"na zdjęciu z {last.day:%d.%m.%Y} działka jest bez roślin (goła gleba)", **seen)

    anchor = green_up(points)
    if anchor is None:
        return _gap("wegetacja na działce jeszcze nie ruszyła, więc nie ma czego porównywać", **seen)
    phase = (last.day - anchor).days
    seen["phase_days"] = phase
    refs = _references(history, group, day.year, phase)
    seen["n_seasons"] = len(refs)

    if after_harvest(points):
        return CropCondition(
            state="ok",
            words=f"Zdjęcie z {last.day:%d.%m.%Y} jest po zbiorze lub pokosie, więc nie ocenia stresu roślin",
            harvest=True,
            ndvi_spread=last.scene.ndvi_spread,
            clear_share=last.scene.valid_fraction,
            ndmi=last.ndmi,
            **seen,  # type: ignore[arg-type]
        )
    if len(refs) < MIN_SEASONS:
        return _gap(
            f"za mało porównywalnych lat: {len(refs)} z {MIN_SEASONS} potrzebnych (ta sama grupa upraw w tej samej fazie rozwoju)",
            ndvi_spread=last.scene.ndvi_spread,
            clear_share=last.scene.valid_fraction,
            **seen,
        )

    grass = group == "tuz"
    own = max(p.ndvi for p in points) if grass else last.ndvi
    ref_ndvi = [r[0] for r in refs]
    weaker_green = own < median(ref_ndvi) - _margin(ref_ndvi, NDVI_MARGIN)
    # Leaf moisture is read only when the canopy is closed and the phase is comparable (not on cut grass).
    ndmi_median = None
    weaker_dry = False
    if not grass and last.ndmi is not None and last.ndvi >= CLOSED_CANOPY_NDVI:
        ref_ndmi = [r[1] for r in refs if r[1] is not None]
        if len(ref_ndmi) >= MIN_SEASONS:
            ndmi_median = round(median(ref_ndmi), 3)
            weaker_dry = last.ndmi < median(ref_ndmi) - _margin(ref_ndmi, NDMI_MARGIN)
    n, when = len(refs), f"zdjęcie z {last.day:%d.%m.%Y}"
    if weaker_green:
        words = f"Rośliny słabsze niż w {n} porównywalnych latach w tej samej fazie rozwoju ({when})"
    elif weaker_dry:
        words = f"Rośliny słabsze (liście bardziej przesuszone) niż w {n} porównywalnych latach w tej samej fazie ({when})"
    else:
        words = f"Rośliny nie odbiegają od {n} porównywalnych lat w tej samej fazie rozwoju ({when})"
    return CropCondition(
        state="ok",
        words=words,
        signal="weaker" if weaker_green or weaker_dry else "normal",
        ndmi=last.ndmi,
        ndmi_median=ndmi_median,
        ndvi_spread=last.scene.ndvi_spread,
        clear_share=last.scene.valid_fraction,
        **seen,  # type: ignore[arg-type]
    )


def _references(
    history: dict[int, list[SceneIndex]], group: SeasonGroup, year: int, phase: int
) -> list[tuple[float, float | None]]:
    """(NDVI, NDMI) of every earlier season of `group` at `phase` days after its own start of vegetation."""
    out: list[tuple[float, float | None]] = []
    for y, readings in sorted(history.items()):
        if y >= year:
            continue
        pts = usable_points(readings)
        if classify_points(pts) != group or (start := green_up(pts)) is None:
            continue
        target = start + timedelta(days=phase)
        if group == "tuz":
            peak = _peak_until(pts, target)
            if peak is not None:
                out.append((peak, None))
        elif (at := _at(pts, target)) is not None:
            out.append((at.ndvi, at.ndmi))
    return out
