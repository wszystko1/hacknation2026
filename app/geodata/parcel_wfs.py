"""Parcel outlines from the EGiB WFS (layer ms:dzialki): the fallback when ULDK does not answer.

Axis order: in EPSG:2180 the BBOX and GML coordinates are northing, easting (urn:ogc:def:crs:EPSG::2180); the
GeoJSON the service returns carries x, y = easting, northing. We read GeoJSON and send BBOX as N,E.
"""

from __future__ import annotations

import json
from typing import Any
from xml.sax.saxutils import escape

from . import config, http
from .errors import ParcelNotFound, UpstreamError
from .models import Parcel

LAYER = "ms:dzialki"
SOURCE = "EGiB WFS"
CRS_URN = "urn:ogc:def:crs:EPSG::2180"
POINT_BOX_M = 2.0
_FILTER_NS = 'xmlns="http://www.opengis.net/fes/2.0"'


def _equal(name: str, value: str) -> str:
    return f"<PropertyIsEqualTo><ValueReference>{name}</ValueReference><Literal>{escape(value)}</Literal></PropertyIsEqualTo>"


def _query(extra: dict[str, str], deadline: float | None) -> list[dict[str, Any]]:
    params = {
        "SERVICE": "WFS",
        "VERSION": "2.0.0",
        "REQUEST": "GetFeature",
        "TYPENAMES": LAYER,
        "SRSNAME": CRS_URN,
        "OUTPUTFORMAT": "application/json",
        **extra,
    }
    resp = http.get(
        config.EGIB_WFS_URL, params=params, timeout=config.EGIB_WFS_TIMEOUT, retries=0, deadline=deadline
    )
    if resp.status_code != 200:
        raise UpstreamError(f"EGiB WFS HTTP {resp.status_code}")
    try:
        body = json.loads(resp.content)
        features = body["features"]
    except (ValueError, KeyError, TypeError) as exc:
        raise UpstreamError("EGiB WFS: the answer is not GeoJSON") from exc
    return [f for f in features if isinstance(f, dict) and f.get("geometry")]


def _rings(geometry: dict[str, Any]) -> tuple[list[list[list[float]]], bool]:
    kind, coords = geometry.get("type"), geometry.get("coordinates")
    if kind == "Polygon":
        return [[[float(p[0]), float(p[1])] for p in ring] for ring in coords], False
    if kind == "MultiPolygon":
        return [[[float(p[0]), float(p[1])] for p in ring] for part in coords for ring in part], True
    raise UpstreamError(f"EGiB WFS: unexpected geometry {kind}")


def _contains(rings: list[list[list[float]]], x: float, y: float) -> bool:
    """Even-odd rule over all rings, so holes and parts of a multi-part parcel work."""
    inside = False
    for ring in rings:
        for (x1, y1), (x2, y2) in zip(ring, ring[1:], strict=False):
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                inside = not inside
    return inside


def _parcel(feature: dict[str, Any]) -> Parcel:
    from .parcel import build_parcel  # parcel.py imports this module

    props = feature.get("properties") or {}
    pid = str(props.get("ID_DZIALKI") or "")
    if not pid:
        raise UpstreamError("EGiB WFS: a feature without ID_DZIALKI")
    rings, multi = _rings(feature["geometry"])
    return build_parcel(
        pid,
        voivodeship=str(props.get("NAZWA_WOJEWODZTWA") or props.get("NAZWA_WOJ") or ""),
        county=str(props.get("NAZWA_POWIATU") or ""),
        commune=str(props.get("NAZWA_GMINY") or ""),
        precinct=str(props.get("NAZWA_OBREBU") or ""),
        number=str(props.get("NUMER_DZIALKI") or pid.rsplit(".", 1)[-1]),
        rings=rings,
        multipolygon=multi,
        source=SOURCE,
    )


def parcel_by_id(parcel_id: str, *, deadline: float | None = None) -> Parcel:
    """Parcel whose ID_DZIALKI equals the identifier. Raises ParcelNotFound or UpstreamError."""
    flt = f"<Filter {_FILTER_NS}>{_equal('ID_DZIALKI', parcel_id)}</Filter>"
    features = _query({"FILTER": flt}, deadline)
    for feature in features:
        if str((feature.get("properties") or {}).get("ID_DZIALKI")) == parcel_id:
            return _parcel(feature)
    raise ParcelNotFound(f"EGiB WFS: no parcel {parcel_id}")


def parcel_at_point(x: float, y: float, *, deadline: float | None = None) -> Parcel:
    """Parcel that contains the EPSG:2180 point (x = easting, y = northing)."""
    half = POINT_BOX_M / 2
    box = f"{y - half:.2f},{x - half:.2f},{y + half:.2f},{x + half:.2f},{CRS_URN}"  # northing first
    features = _query({"BBOX": box}, deadline)
    for feature in features:
        rings, _ = _rings(feature["geometry"])
        if _contains(rings, x, y):
            return _parcel(feature)
    raise ParcelNotFound("EGiB WFS: no parcel at this point")


def parcels_by_name(precinct: str, number: str, *, deadline: float | None = None) -> list[Parcel]:
    """Parcels with this precinct name and number. Raises ParcelNotFound or UpstreamError."""
    flt = f"<Filter {_FILTER_NS}><And>{_equal('NAZWA_OBREBU', precinct)}{_equal('NUMER_DZIALKI', number)}</And></Filter>"
    found = [_parcel(f) for f in _query({"FILTER": flt}, deadline)]
    found = [
        p
        for p in found
        if p.precinct.casefold() == precinct.casefold() and p.number.casefold() == number.casefold()
    ]
    if not found:
        raise ParcelNotFound(f"EGiB WFS: no parcel {precinct} {number}")
    return found
