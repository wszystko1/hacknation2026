"""Cadastral parcel lookup in ULDK (GUGiK): geometry, administrative names, area."""

from __future__ import annotations

import re
import threading
from collections.abc import Callable
from dataclasses import asdict

from pyproj import Transformer

from . import cache, config, parcel_wfs, uldk_guard
from .errors import InvalidParcelId, ParcelNotFound, UpstreamError
from .models import Parcel, SourceResult, now_iso
from .samples import list_samples

RESULT_FIELDS = "id,voivodeship,county,commune,region,parcel,geom_wkt"
RESOLUTION = "EGiB cadastral geometry (vector, EPSG:2180)"

# TERYT commune code (6 digits) + "_" + commune type digit, precinct (4 digits), optional map sheet, number.
_ID_RE = re.compile(r"^(\d{6}_\d)\.(\d{4})\.((?:[Aa][Rr]_\d+\.)?)([0-9A-Za-z/_.\-]+)$")
_PAIR_RE = re.compile(r"(-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?)")
_local = threading.local()


def normalize_parcel_id(text: str) -> str:
    """Trim, unify separators and validate. Raises InvalidParcelId with a format hint."""
    raw = re.sub(r"\s+", "", (text or "").strip()).replace("\\", "/").replace(",", ".")
    match = _ID_RE.match(raw)
    if not match:
        raise InvalidParcelId(
            f"'{text}' is not a parcel identifier; expected TERYT_type.precinct.number, e.g. 040303_2.0004.121/7"
        )
    commune, precinct, sheet, number = match.groups()
    return f"{commune}.{precinct}.{sheet.upper()}{number}"


def _to_wgs() -> Transformer:
    if not hasattr(_local, "t"):
        _local.t = Transformer.from_crs(2180, 4326, always_xy=True)
    return _local.t


def _to_2180() -> Transformer:
    if not hasattr(_local, "t2180"):
        _local.t2180 = Transformer.from_crs(4326, 2180, always_xy=True)
    return _local.t2180


def to_wgs84(x: float, y: float) -> list[float]:
    lon, lat = _to_wgs().transform(x, y)
    return [round(lon, 7), round(lat, 7)]


def parse_wkt_rings(wkt: str) -> list[list[list[float]]]:
    """Rings of a POLYGON/MULTIPOLYGON WKT (optional SRID prefix). Outer ring of the largest part first."""
    body = wkt.split(";", 1)[-1]
    rings = [
        [[float(a), float(b)] for a, b in _PAIR_RE.findall(chunk)]
        for chunk in re.findall(r"\(([^()]+)\)", body)
    ]
    rings = [r for r in rings if len(r) >= 4]
    if not rings:
        raise UpstreamError(f"cannot parse geometry: {wkt[:80]}")
    if body.upper().startswith("MULTIPOLYGON"):
        rings.sort(key=lambda r: -abs(_ring_area(r)))
    return rings


def _ring_area(ring: list[list[float]]) -> float:
    return sum(ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1] for i in range(len(ring) - 1)) / 2.0


def _ring_centroid(ring: list[list[float]]) -> list[float]:
    area = _ring_area(ring)
    if abs(area) < 1e-9:
        return [sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)]
    cx = cy = 0.0
    for i in range(len(ring) - 1):
        cross = ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1]
        cx += (ring[i][0] + ring[i + 1][0]) * cross
        cy += (ring[i][1] + ring[i + 1][1]) * cross
    return [cx / (6 * area), cy / (6 * area)]


def parse_uldk(text: str, *, multipolygon: bool = False) -> Parcel:
    """Parse a ULDK answer: first line status ("0" = ok), second line fields separated by "|"."""
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    if not lines or lines[0] != "0" or len(lines) < 2:
        raise ParcelNotFound(f"ULDK: {' '.join(lines)[:120] or 'empty answer'}")
    parts = lines[1].split("|")
    if len(parts) < 7:
        raise UpstreamError(f"ULDK: unexpected answer: {lines[1][:120]}")
    pid, voiv, county, commune, precinct, number = parts[:6]
    rings = parse_wkt_rings(parts[6])
    return build_parcel(
        pid, voivodeship=voiv, county=county, commune=commune, precinct=precinct, number=number,
        rings=rings, multipolygon="MULTIPOLYGON" in parts[6].upper(), source="ULDK",
    )  # fmt: skip


def build_parcel(
    pid: str,
    *,
    voivodeship: str,
    county: str,
    commune: str,
    precinct: str,
    number: str,
    rings: list[list[list[float]]],
    multipolygon: bool,
    source: str,
) -> Parcel:
    """The Parcel of any source: the area is computed from the geometry, the source is recorded."""
    rings = [r for r in rings if len(r) >= 4]
    if not rings:
        raise UpstreamError(f"no usable geometry for {pid}")
    if multipolygon:
        rings.sort(key=lambda r: -abs(_ring_area(r)))
    # For a plain polygon: outer ring minus holes. For multi-part parcels all parts count as area.
    outer = abs(_ring_area(rings[0]))
    rest = sum(abs(_ring_area(r)) for r in rings[1:])
    area_m2 = outer + rest if multipolygon else outer - rest
    xs = [p[0] for r in rings for p in r]
    ys = [p[1] for r in rings for p in r]
    centroid = _ring_centroid(rings[0])
    lo, hi = to_wgs84(min(xs), min(ys)), to_wgs84(max(xs), max(ys))
    return Parcel(
        id=pid,
        voivodeship=voivodeship,
        county=county,
        commune=commune,
        precinct=precinct,
        number=number,
        area_ha=round(area_m2 / 1e4, 4),
        rings_2180=[[[round(x, 2), round(y, 2)] for x, y in r] for r in rings],
        rings_4326=[[to_wgs84(x, y) for x, y in r] for r in rings],
        centroid_2180=[round(centroid[0], 2), round(centroid[1], 2)],
        centroid_4326=to_wgs84(*centroid),
        bbox_2180=[round(min(xs), 2), round(min(ys), 2), round(max(xs), 2), round(max(ys), 2)],
        bbox_4326=[lo[0], lo[1], hi[0], hi[1]],
        outline_source=source,
    )


def _local_ids() -> str:
    return ", ".join(sorted({pid for pid, _ in list_samples()}))


def both_failed_message() -> str:
    """The sentence shown when ULDK and the EGiB WFS gave nothing (Polish: the user reads it)."""
    ids = _local_ids()
    tail = f" Bez nich działają tylko działki z kopią lokalną: {ids}." if ids else ""
    return f"Usługi GUGiK (ULDK i EGiB WFS) nie odpowiedziały.{tail}"


def _result(parcel: Parcel, url: str, retrieved_at: str, *, from_cache: bool = False) -> SourceResult[Parcel]:
    return SourceResult(
        "parcel", "ok", parcel, source_url=url, retrieved_at=retrieved_at, resolution=RESOLUTION,
        from_cache=from_cache,
    )  # fmt: skip


def _store(cache_key: str, parcel: Parcel, url: str) -> SourceResult[Parcel]:
    entry = {"data": asdict(parcel), "url": url, "retrieved_at": now_iso()}
    cache.put_json("parcel", cache_key, entry)
    if cache_key != parcel.id:
        cache.put_json("parcel", parcel.id, entry)
    return _result(parcel, url, entry["retrieved_at"])


def _lookup(
    cache_key: str,
    params: dict[str, str],
    deadline: float | None,
    wfs: Callable[[], Parcel],
) -> SourceResult[Parcel]:
    """Local copy, then ULDK (guarded), then the EGiB WFS; an honest error when none answers."""
    hit = cache.get_json("parcel", cache_key, config.TTL_PARCEL)
    if hit is not None:
        parcel = Parcel(**hit["data"])  # keeps the source the outline was first fetched from
        return _result(parcel, hit["url"], hit["retrieved_at"], from_cache=True)
    cache.require_online("parcel", cache_key)
    try:
        answer = uldk_guard.fetch(params, geometry=True, deadline=deadline)
        return _store(cache_key, parse_uldk(answer.text), answer.url)
    except UpstreamError:
        pass  # the decoy, silence or an error of ULDK: ask the EGiB WFS
    try:
        return _store(cache_key, wfs(), config.EGIB_WFS_URL)
    except ParcelNotFound:
        raise
    except UpstreamError as exc:
        raise UpstreamError(both_failed_message()) from exc


def fetch_parcel(parcel_id: str, *, deadline: float | None = None) -> SourceResult[Parcel]:
    """Parcel by identifier. Raises InvalidParcelId, ParcelNotFound, UpstreamError or CacheMiss."""
    pid = normalize_parcel_id(parcel_id)
    params = {"request": "GetParcelById", "id": pid, "result": RESULT_FIELDS, "srid": "2180"}
    return _lookup(pid, params, deadline, lambda: parcel_wfs.parcel_by_id(pid, deadline=deadline))


def fetch_parcel_by_lonlat(lon: float, lat: float, *, deadline: float | None = None) -> SourceResult[Parcel]:
    """Parcel that contains the WGS84 point."""
    key = f"xy_{lon:.6f}_{lat:.6f}"
    params = {"request": "GetParcelByXY", "xy": f"{lon},{lat},4326", "result": RESULT_FIELDS, "srid": "2180"}
    x, y = _to_2180().transform(lon, lat)
    return _lookup(key, params, deadline, lambda: parcel_wfs.parcel_at_point(x, y, deadline=deadline))
