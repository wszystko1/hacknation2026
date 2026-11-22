"""Typed result objects. Everything is a plain dataclass that converts to JSON with to_dict()."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Generic, Literal, TypeVar

Status = Literal["ok", "fallback", "timeout", "error", "skipped"]
T = TypeVar("T")


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class SourceResult(Generic[T]):
    """Outcome of one data source. `data` is None unless status is ok or fallback."""

    source: str
    status: Status
    data: T | None = None
    elapsed_ms: int = 0
    source_url: str = ""
    retrieved_at: str = ""  # ISO timestamp (UTC) of the original download, also for cache hits
    resolution: str = ""  # e.g. "ERA5 grid ~9-25 km"
    notes: list[str] = field(default_factory=list)
    error: str = ""
    from_cache: bool = False

    @property
    def usable(self) -> bool:
        return self.status in ("ok", "fallback") and self.data is not None


@dataclass
class Parcel:
    id: str
    voivodeship: str
    county: str
    commune: str
    precinct: str
    number: str
    area_ha: float
    rings_2180: list[
        list[list[float]]
    ]  # [ring][vertex][x=easting, y=northing], EPSG:2180, first ring = outline
    rings_4326: list[list[list[float]]]  # [ring][vertex][lon, lat]
    centroid_2180: list[float]  # [x, y]
    centroid_4326: list[float]  # [lon, lat]
    bbox_2180: list[float]  # [xmin, ymin, xmax, ymax]
    bbox_4326: list[float]  # [lonmin, latmin, lonmax, latmax]


@dataclass
class Ortho:
    image: bytes  # JPEG
    content_type: str
    width: int
    height: int
    bbox_2180: list[float]  # [xmin, ymin, xmax, ymax] of the image
    m_per_px: float
    polygon_px: list[list[list[float]]]  # [ring][vertex][col, row], origin top-left


@dataclass
class Weather:
    provider: str  # chain summary, e.g. "open-meteo-archive" or "imgw+nasa-power"
    latitude: float  # grid point of the gridded provider (or the requested point)
    longitude: float
    dates: list[str]  # ISO days, ascending, continuous, last one <= requested date
    precipitation_mm: list[float | None]
    et0_mm: list[float | None]  # FAO-56 Penman-Monteith reference evapotranspiration
    recent_filled_from: str = ""  # first day taken from the forecast model, "" if none
    missing_days: int = 0
    missing_share: float = 0.0  # share of days in the range without precipitation or ET0
    precipitation_provider: str = ""  # provider of most precipitation days in the range
    et0_provider: str = ""
    precipitation_sources: dict[str, float] = field(default_factory=dict)  # provider -> share of days
    et0_sources: dict[str, float] = field(default_factory=dict)
    precipitation_station: str = ""  # nearest IMGW station used, "" for gridded data
    precipitation_station_km: float | None = None
    et0_station: str = ""
    et0_station_km: float | None = None
    grid: str = ""  # grid size of the gridded provider(s) used
    tmean_c: list[float | None] = field(default_factory=list)  # daily mean temperature, aligned with `dates`
    sunshine_h: list[float | None] = field(default_factory=list)  # daily sunshine hours, aligned with `dates`


@dataclass
class Forecast:
    dates: list[str]  # today and the following days
    precipitation_mm: list[float | None]
    et0_mm: list[float | None]
    days: int = 0


@dataclass
class Seasonal:
    dates: list[str]
    precipitation_mean_mm: list[float | None]  # ensemble mean per day
    precipitation_p10_mm: list[float | None]
    precipitation_p90_mm: list[float | None]
    et0_mean_mm: list[float | None]
    members: int = 0


@dataclass
class Soil:
    sand_pct: float | None  # 0-30 cm, thickness-weighted mean
    silt_pct: float | None
    clay_pct: float | None
    texture_class: str | None  # USDA texture class name (English key), None when unknown
    available: bool = False


@dataclass
class SceneIndex:
    scene_id: str
    date: str
    days_from_target: int
    cloud_cover_pct: float | None
    ndvi: float | None
    ndmi: float | None
    valid_fraction: float  # share of parcel pixels left after the SCL mask
    pixels: int
    ndvi_spread: float | None = None  # spread (p90 - p10) of NDVI between the clear pixels of the parcel


@dataclass
class Satellite:
    target_date: str
    current: SceneIndex | None  # nearest usable scene to the target date
    history: list[SceneIndex] = field(default_factory=list)  # same time of year in earlier years
    candidates: int = 0  # scenes found in the search window
    seasons: dict[int, list[SceneIndex]] = field(
        default_factory=dict
    )  # year -> readings of that whole season


@dataclass
class ElevationGrid:
    """North-up grid. Cell (row, col) has its centre at (x0 + (col + 0.5) * step_m, y_top - (row + 0.5) * step_m)."""

    crs: str  # "EPSG:2180"
    x0: float  # western edge (easting)
    y_top: float  # northern edge (northing)
    step_m: float
    rows: int
    cols: int
    z: list[list[float | None]]  # elevation in metres, None where unknown
    inside: list[list[int]]  # 1 where the cell centre lies inside the parcel


@dataclass
class Terrain:
    min_m: float
    max_m: float
    mean_m: float
    slope_mean_pct: float | None
    slope_max_pct: float | None
    lowest_outline_point_2180: list[float] | None  # [x, y]
    lowest_outline_point_4326: list[float] | None  # [lon, lat]
    lowest_outline_elevation_m: float | None
    grid_m: float  # sample spacing in metres
    samples: int  # cells inside the parcel
    provider: str  # "gugik-nmt-points", "gugik-nmt-wcs" or "open-meteo-elevation"
    grid: ElevationGrid | None = None  # parcel bbox plus margin
    catchment_grid: ElevationGrid | None = (
        None  # outline plus ~300 m, one step for the whole grid; D8 accumulation only
    )
    catchment_note: str = ""  # what was downloaded for catchment_grid (Polish, shown to the user)


@dataclass
class WaterFeature:
    kind: str  # "ditch", "stream", "canal" or "water_body"
    distance_m: float  # from the parcel boundary; 0 when it touches or crosses the parcel
    area_m2: float  # drawn area on the map raster (line width is a map symbol, not the real width)
    rings_2180: list[list[list[float]]]  # outline traced from the map raster


@dataclass
class Water:
    provider: str
    search_m: float  # features are searched within this distance of the parcel bbox
    pixel_m: float
    features: list[WaterFeature]
    nearest_ditch_m: float | None  # None: no ditch within search_m
    nearest_stream_m: float | None
    nearest_canal_m: float | None
    nearest_water_body_m: float | None
    nearest_any_m: float | None
    nearest_any_kind: str | None


@dataclass
class CropClass:
    code: int
    name: str
    share: float


@dataclass
class CropHint:
    map_year: int
    classes: list[CropClass]  # shares of parcel pixels, largest first
    dominant: str | None
    pixels: int


@dataclass
class FetchResult:
    parcel_id: str
    date: str
    total_ms: int
    budget_s: float
    parcel: SourceResult[Parcel]
    weather: SourceResult[Weather]
    ortho: SourceResult[Ortho]
    soil: SourceResult[Soil]
    satellite: SourceResult[Satellite]
    terrain: SourceResult[Terrain]
    water: SourceResult[Water]
    forecast: SourceResult[Forecast]
    seasonal: SourceResult[Seasonal]
    crop_hint: SourceResult[CropHint]

    @property
    def core_ok(self) -> bool:
        """True when the two core sources (parcel, weather) are usable."""
        return self.parcel.usable and self.weather.usable

    def sources(self) -> dict[str, SourceResult[Any]]:
        return {n: getattr(self, n) for n in SOURCE_TYPES}

    def to_dict(self, *, include_image: bool = False) -> dict[str, Any]:
        """JSON-ready dict. The JPEG is dropped unless include_image (then base64)."""
        return to_jsonable(self, include_image=include_image) | {"core_ok": self.core_ok}


def to_jsonable(obj: Any, *, include_image: bool = False) -> Any:
    import base64

    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {
            f.name: to_jsonable(getattr(obj, f.name), include_image=include_image)
            for f in dataclasses.fields(obj)
        }
    if isinstance(obj, bytes):
        return base64.b64encode(obj).decode("ascii") if include_image else None
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v, include_image=include_image) for v in obj]
    if isinstance(obj, dict):
        return {k: to_jsonable(v, include_image=include_image) for k, v in obj.items()}
    return obj


SOURCE_TYPES: dict[str, type] = {
    "parcel": Parcel, "weather": Weather, "ortho": Ortho, "soil": Soil, "satellite": Satellite,
    "terrain": Terrain, "water": Water, "forecast": Forecast, "seasonal": Seasonal, "crop_hint": CropHint,
}  # fmt: skip


def from_dict(cls: type, data: Any) -> Any:
    """Rebuild a dataclass (with nested dataclasses and lists of them) from its to_jsonable() form."""
    import types
    import typing

    if data is None or not dataclasses.is_dataclass(cls):
        return data
    hints = typing.get_type_hints(cls)
    kwargs = {}
    for f in dataclasses.fields(cls):
        if f.name not in data:
            continue
        value, hint = data[f.name], hints[f.name]
        if typing.get_origin(hint) in (typing.Union, types.UnionType):
            hint = next((a for a in typing.get_args(hint) if a is not type(None)), hint)
        if dataclasses.is_dataclass(hint):
            value = from_dict(hint, value)
        elif typing.get_origin(hint) is list and value is not None:
            (inner,) = typing.get_args(hint)
            if dataclasses.is_dataclass(inner):
                value = [from_dict(inner, v) for v in value]
        elif typing.get_origin(hint) is dict and isinstance(value, dict):
            key_type, item = typing.get_args(hint)
            inner = typing.get_args(item)[0] if typing.get_origin(item) is list else item
            if key_type is int:  # JSON object keys are strings
                value = {int(k): v for k, v in value.items()}
            if dataclasses.is_dataclass(inner):
                value = {
                    k: [from_dict(inner, x) for x in v] if isinstance(v, list) else from_dict(inner, v)
                    for k, v in value.items()
                }
        kwargs[f.name] = value
    return cls(**kwargs)
