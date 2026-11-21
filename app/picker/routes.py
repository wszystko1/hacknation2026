"""Routes of the parcel picker: parcel under a map point and the map tiles. See contracts/api.md."""

from __future__ import annotations

import math
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response

from app.geodata import config, fetch_parcel_by_lonlat
from app.geodata.errors import GeodataError, ParcelNotFound
from app.picker import frozen, tiles

router = APIRouter()

# Rectangle around Poland with a margin; a point outside it is refused without asking ULDK.
POLAND_LON = (14.0, 24.3)
POLAND_LAT = (48.9, 55.0)
LIVE_WAIT_S = 6.0

_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="uldk-xy")


def _refuse(message: str) -> JSONResponse:
    return JSONResponse({"bledy": [{"field": "dzialka", "message": message}]}, status_code=422)


def _number(raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        value = float(raw.strip().replace(",", "."))
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _live(lon: float, lat: float) -> dict:
    """ULDK answer for the point; the thread is abandoned after LIVE_WAIT_S so a click never hangs."""
    future = _pool.submit(fetch_parcel_by_lonlat, lon, lat, deadline=time.monotonic() + LIVE_WAIT_S)
    parcel = future.result(timeout=LIVE_WAIT_S + 1).data
    assert parcel is not None
    return {
        "dzialka": parcel.id,
        "numer": parcel.number,
        "obreb": parcel.precinct,
        "gmina": parcel.commune,
        "pow_ha": round(parcel.area_ha, 2),
        "obrys_4326": parcel.rings_4326,
    }


@router.get("/api/dzialka")
def parcel_at_point(lon: str | None = None, lat: str | None = None) -> JSONResponse:
    x, y = _number(lon), _number(lat)
    if x is None or y is None:
        return _refuse(
            "Podaj długość i szerokość geograficzną punktu jako liczby, np. lon=18.1353&lat=53.2705."
        )
    if not (POLAND_LON[0] <= x <= POLAND_LON[1] and POLAND_LAT[0] <= y <= POLAND_LAT[1]):
        return _refuse("Ten punkt leży poza Polską. Wskaż działkę na mapie kraju.")
    hit = frozen.find(x, y)
    if hit is not None:
        return JSONResponse(hit.as_answer())
    if config.is_offline():
        return _refuse(
            "Bez sieci znamy tylko działki demonstracyjne i ich sąsiadów. Wskaż inny punkt albo wpisz numer działki."
        )
    try:
        return JSONResponse(_live(x, y))
    except ParcelNotFound:
        return _refuse("W tym punkcie nie ma działki ewidencyjnej. Kliknij w pole albo wpisz numer działki.")
    except (GeodataError, FutureTimeout, AssertionError):
        return _refuse(
            "Nie mamy odpowiedzi z ewidencji gruntów (ULDK). Spróbuj za chwilę albo wpisz numer działki."
        )


@router.get("/mapa/kafel/{layer}/{z}/{x}/{y}.jpg")
def map_tile(layer: str, z: int, x: int, y: int) -> Response:
    if not tiles.valid_address(layer, z, x, y):
        return Response(status_code=404)
    image, real = tiles.get_tile(layer, z, x, y)
    cache = "public, max-age=86400" if real else "no-store"
    return Response(image, media_type="image/jpeg", headers={"Cache-Control": cache})
