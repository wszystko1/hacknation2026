"""Data acquisition layer: parcel geometry, orthophoto, weather, soil, satellite indices, terrain.

Typical use:

    from app.geodata import fetch_all
    result = fetch_all("040303_2.0004.121/7", "2026-07-15", budget_s=25)
    if result.core_ok:
        days, rain, et0 = result.weather.data.dates, result.weather.data.precipitation_mm, result.weather.data.et0_mm
"""

from .crop_hint import fetch_crop_hint
from .errors import CacheMiss, GeodataError, InvalidParcelId, ParcelNotFound, UpstreamError
from .forecast import fetch_forecast, fetch_seasonal
from .models import (
    CropHint,
    ElevationGrid,
    FetchResult,
    Forecast,
    Ortho,
    Parcel,
    Satellite,
    SceneIndex,
    Seasonal,
    Soil,
    SourceResult,
    Terrain,
    Water,
    WaterFeature,
    Weather,
)
from .orchestrator import ALL_SOURCES, CORE_SOURCES, fetch_all
from .ortho import fetch_ortho
from .parcel import fetch_parcel, fetch_parcel_by_lonlat, normalize_parcel_id
from .samples import list_samples, load_sample
from .satellite import fetch_satellite
from .soil import fetch_soil
from .terrain import fetch_terrain
from .water import fetch_water
from .weather import fetch_weather

__all__ = [
    "CropHint",
    "ElevationGrid",
    "Forecast",
    "Seasonal",
    "Water",
    "WaterFeature",
    "fetch_crop_hint",
    "fetch_forecast",
    "fetch_seasonal",
    "fetch_water",
    "ALL_SOURCES",
    "CORE_SOURCES",
    "CacheMiss",
    "FetchResult",
    "GeodataError",
    "InvalidParcelId",
    "Ortho",
    "Parcel",
    "ParcelNotFound",
    "Satellite",
    "SceneIndex",
    "Soil",
    "SourceResult",
    "Terrain",
    "UpstreamError",
    "Weather",
    "fetch_all",
    "fetch_ortho",
    "fetch_parcel",
    "fetch_parcel_by_lonlat",
    "fetch_satellite",
    "fetch_soil",
    "fetch_terrain",
    "fetch_weather",
    "list_samples",
    "load_sample",
    "normalize_parcel_id",
]
