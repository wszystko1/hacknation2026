"""Runtime configuration of the data layer (environment variables, timeouts, endpoints)."""

from __future__ import annotations

import os
from pathlib import Path

USER_AGENT = "geodata-client/0.1 (python-httpx)"

ULDK_URL = "https://uldk.gugik.gov.pl/"
EGIB_WFS_URL = "https://mapy.geoportal.gov.pl/wss/service/PZGIK/EGIB/WFS/UslugaZbiorcza"
EGIB_WFS_TIMEOUT = 5.0
ORTHO_WMS_URL = "https://mapy.geoportal.gov.pl/wss/service/PZGIK/ORTO/WMS/StandardResolution"
OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"
NASA_POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
SOILGRIDS_URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"
# Sentinel-2 COGs: Planetary Computer (Azure West Europe) is the default because the Earth Search COGs
# (AWS us-west-2) downloaded at ~50 kB/s from Poland in our measurement. GEODATA_STAC=earth-search switches.
STAC_URLS = {
    "planetary-computer": "https://planetarycomputer.microsoft.com/api/stac/v1/search",
    "earth-search": "https://earth-search.aws.element84.com/v1/search",
}
PC_TOKEN_URL = "https://planetarycomputer.microsoft.com/api/sas/v1/token/sentinel-2-l2a"
NMT_WCS_URL = "https://mapy.geoportal.gov.pl/wss/service/PZGIK/NMT/GRID1/WCS/DigitalTerrainModelFormatTIFF"
NMT_COVERAGE = "DTM_PL-KRON86-NH_TIFF"

# Per-source wall-clock limits in seconds (the orchestrator also enforces the total budget).
TIMEOUTS: dict[str, float] = {
    "parcel": 9.0,
    "weather": 12.0,
    "ortho": 12.0,
    "soil": 7.0,
    "satellite": 18.0,
    "terrain": 10.0,
}

DAY = 86400.0
# Cache lifetimes in seconds; None means "immutable, keep forever".
TTL_PARCEL: float | None = 30 * DAY
TTL_ORTHO: float | None = 30 * DAY
TTL_WEATHER_RECENT: float | None = 6 * 3600.0
TTL_SOIL_NULL: float | None = DAY
TTL_SATELLITE_RECENT: float | None = 12 * 3600.0

_offline_override: bool | None = None


def repo_root() -> Path:
    """Repository root: two levels above this package (app/geodata -> repo)."""
    return Path(__file__).resolve().parents[2]


def cache_dir() -> Path:
    """Cache directory; override with GEODATA_CACHE_DIR. Default: <repo>/data/raw/geodata_cache."""
    env = os.environ.get("GEODATA_CACHE_DIR")
    return Path(env) if env else repo_root() / "data" / "raw" / "geodata_cache"


def demo_dir() -> Path:
    """Committed small samples used when neither network nor cache is available."""
    return repo_root() / "demo" / "data" / "geodata"


def is_offline() -> bool:
    """Offline mode serves only from the cache. Set GEODATA_OFFLINE=1 or call set_offline(True)."""
    if _offline_override is not None:
        return _offline_override
    return os.environ.get("GEODATA_OFFLINE", "").strip().lower() in {"1", "true", "yes"}


def set_offline(value: bool | None) -> None:
    global _offline_override
    _offline_override = value


def imgw_only_weather() -> bool:
    """GEODATA_WEATHER=imgw skips the Open-Meteo archive, so a series does not depend on its daily limit."""
    return os.environ.get("GEODATA_WEATHER", "").strip().lower() == "imgw"


def stac_provider() -> str:
    name = os.environ.get("GEODATA_STAC", "planetary-computer").strip().lower()
    return name if name in STAC_URLS else "planetary-computer"


def stac_search_url() -> str:
    return STAC_URLS[stac_provider()]


NMT_POINTS_URL = "https://services.gugik.gov.pl/nmt/"
BDOT_WMS_URL = (
    "https://mapy.geoportal.gov.pl/wss/service/pub/guest/kompozycja_BDOT10k_WMS/MapServer/WMSServer"
)
OPEN_METEO_SEASONAL_URL = "https://seasonal-api.open-meteo.com/v1/seasonal"
EUCROPMAP_URL = (
    "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/EUCROPMAP/2022/EU_CropMap_22_v1_stratum_EU27-HR.tif"
)
TIMEOUTS.update({"water": 10.0, "forecast": 6.0, "seasonal": 6.0, "crop_hint": 8.0})

# Sources that run in the background of a live request: the report waits for them only this long after the
# others have answered; they keep running up to BACKGROUND_S and land in the cache for the next request.
BACKGROUND_GRACE_S = 2.0
BACKGROUND_S = 60.0

# A host that timed out is skipped this long; the geodata cache and the map tile cache are capped on disk.
HOST_FAILURE_TTL_S = 300.0
GEODATA_CACHE_MAX_BYTES = 2 * 1024**3
TILE_CACHE_MAX_BYTES = 500 * 1024**2
