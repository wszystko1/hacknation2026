"""Reading and checking the three fields (działka, data, uprawa) and the report options from a query string.

The "Działka" field takes three forms: the full identifier (040303_2.0002.189/13), the precinct name with the
number ("Dobrcz 189/13", ULDK GetParcelByIdOrNr, a list to choose from when several parcels fit) and coordinates
("53,2705 18,1353" in WGS84 or "442332 600940" in EPSG:2180). The date is typed and shown as dd.mm.rrrr.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from pyproj import Transformer

from app.geodata import (
    CacheMiss,
    GeodataError,
    InvalidParcelId,
    ParcelNotFound,
    UpstreamError,
    cache,
    config,
    fetch_parcel_by_lonlat,
    list_samples,
    load_sample,
    normalize_parcel_id,
    parcel_wfs,
    uldk_guard,
)
from app.geodata.models import Parcel
from app.geodata.parcel import both_failed_message
from app.models import SOIL_CATEGORIES, CropGroup, FieldError, ReportRequest

FIRST_DAY = date(2016, 1, 1)

ID_HINT = "040303_2.0002.189/13"
FORMAT_ERROR = (
    f"Numer ma postać {ID_HINT} albo obręb i numer, np. Dobrcz 189/13, albo współrzędne, np. 53,2705 18,1353"
)
NAME_FIELDS = "id,voivodeship,county,commune,region,parcel"

_DATE_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$")
_NUMBER = r"-?\d+(?:[.,]\d+)?"
_PAIR_RE = re.compile(rf"^({_NUMBER})\s*(?:;|,\s|\s)\s*({_NUMBER})$")
_NAME_RE = re.compile(r"^(?P<precinct>[^\d\s][^\d]*?)[\s,]+(?P<number>\d[0-9A-Za-z/_.\-]*)$")
_to_wgs = Transformer.from_crs(2180, 4326, always_xy=True)


class ParcelLookupError(Exception):
    """The "Działka" text led to no single parcel; `message` is shown next to the field."""

    def __init__(self, message: str, choices: list[ParcelChoice] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.choices = choices or []


@dataclass(frozen=True)
class ParcelChoice:
    id: str
    label: str  # "189/13 · obręb Dobrcz, gm. Dobrcz, powiat bydgoski"


# ------------------------------------------------------------------ date


def parse_date(text: str) -> date:
    """dd.mm.rrrr (the form the field shows) or rrrr-mm-dd (links and the API). Raises ValueError."""
    text = (text or "").strip()
    m = _DATE_RE.match(text)
    if m:
        d, mo, y = (int(g) for g in m.groups())
        return date(y, mo, d)
    return date.fromisoformat(text)


def display_date(text: str) -> str:
    """The date as the field shows it: dd.mm.rrrr; text that is not a date stays as typed."""
    try:
        return f"{parse_date(text):%d.%m.%Y}"
    except ValueError:
        return (text or "").strip()


# ------------------------------------------------------------------ parcel: three forms


def _numbers(text: str) -> tuple[float, float] | None:
    text = text.strip()
    if ";" in text:  # "53,2705; 18,1353": the comma is the decimal separator
        parts = [p.strip() for p in text.split(";")]
        if len(parts) != 2:
            return None
        text = " ".join(parts)
    m = _PAIR_RE.match(text)
    if not m:
        return None
    return float(m.group(1).replace(",", ".")), float(m.group(2).replace(",", "."))


def parse_coordinates(text: str) -> tuple[float, float] | None:
    """(lon, lat) in WGS84 from "lat lon", "lon lat" (the order is told by the range over Poland) or EPSG:2180 "x y"."""
    pair = _numbers(text)
    if pair is None:
        return None
    a, b = pair
    if abs(a) > 1000 and abs(b) > 1000:  # EPSG:2180 metres: northing is the second number in "x y" order
        lon, lat = _to_wgs.transform(a, b)
        return (lon, lat) if 49 <= lat <= 55.5 and 14 <= lon <= 24.5 else None
    for lat, lon in ((a, b), (b, a)):
        if 49 <= lat <= 55.5 and 14 <= lon <= 24.5:
            return lon, lat
    return None


def _label(number: str, precinct: str, commune: str, county: str) -> str:
    return f"{number} · obręb {precinct}, gm. {commune}, {county}"


def _inside(ring: list[list[float]], lon: float, lat: float) -> bool:
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:], strict=False):
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _sample_parcels() -> list[Parcel]:
    """Parcels of the committed copies, one per identifier."""
    found: dict[str, Parcel] = {}
    for pid, day in list_samples():
        if pid in found:
            continue
        sample = load_sample(pid, day)
        if sample is not None and sample.parcel.data is not None:
            found[pid] = sample.parcel.data
    return list(found.values())


def _by_point(lon: float, lat: float) -> str:
    try:
        return fetch_parcel_by_lonlat(lon, lat).data.id
    except (CacheMiss, UpstreamError, ParcelNotFound) as exc:
        for parcel in _sample_parcels():
            if _inside(parcel.rings_4326[0], lon, lat):
                return parcel.id
        if isinstance(exc, ParcelNotFound):
            raise ParcelLookupError(
                "W tym miejscu ULDK nie zna działki. Sprawdź współrzędne albo wpisz numer działki"
            ) from exc
        raise ParcelLookupError(
            "Nie udało się zapytać ULDK ani EGiB WFS o te współrzędne. Wpisz pełny numer działki albo spróbuj za chwilę"
        ) from exc


def _parse_name_lines(text: str) -> list[ParcelChoice]:
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    if not lines or lines[0] != "0":
        raise ParcelNotFound(f"ULDK: {' '.join(lines)[:120] or 'empty answer'}")
    found: dict[str, ParcelChoice] = {}
    for line in lines[1:]:
        parts = line.split("|")
        if len(parts) < 6:
            raise UpstreamError(f"ULDK: unexpected answer: {line[:120]}")
        pid, _, county, commune, precinct, number = parts[:6]
        found[pid] = ParcelChoice(pid, _label(number, precinct, commune, county))
    if not found:
        raise ParcelNotFound("ULDK: empty answer")
    return list(found.values())


def _by_name_from_uldk(precinct: str, number: str) -> list[ParcelChoice]:
    """ULDK GetParcelByIdOrNr with "<precinct> <number>". The answer has one line per matching parcel."""
    query = f"{precinct} {number}"
    key = f"name_{query.casefold()}"
    hit = cache.get_json("parcel", key, config.TTL_PARCEL)
    if hit is not None:
        return [ParcelChoice(**c) for c in hit]
    cache.require_online("parcel", key)
    params = {"request": "GetParcelByIdOrNr", "id": query, "result": NAME_FIELDS, "srid": "2180"}
    try:
        choices = _parse_name_lines(uldk_guard.fetch(params, geometry=False).text)
    except UpstreamError:  # the decoy, silence or an error of ULDK: the EGiB WFS knows the precinct names too
        try:
            found = parcel_wfs.parcels_by_name(precinct, number)
        except ParcelNotFound:
            raise
        except UpstreamError as exc:
            raise UpstreamError(both_failed_message()) from exc
        choices = [ParcelChoice(p.id, _label(p.number, p.precinct, p.commune, p.county)) for p in found]
    cache.put_json("parcel", key, [{"id": c.id, "label": c.label} for c in choices])
    return choices


def _by_name_from_samples(precinct: str, number: str) -> list[ParcelChoice]:
    return [
        ParcelChoice(p.id, _label(p.number, p.precinct, p.commune, p.county))
        for p in _sample_parcels()
        if p.precinct.casefold() == precinct.casefold() and p.number.casefold() == number.casefold()
    ]


def _by_name(precinct: str, number: str) -> list[ParcelChoice]:
    try:
        return _by_name_from_uldk(precinct, number)
    except (CacheMiss, UpstreamError, ParcelNotFound) as exc:
        found = _by_name_from_samples(precinct, number)
        if found:
            return found
        if isinstance(exc, ParcelNotFound):
            raise ParcelLookupError(
                f"ULDK nie zna działki „{precinct} {number}”. Sprawdź nazwę obrębu i numer"
            ) from exc
        raise ParcelLookupError(
            "Nie udało się zapytać ULDK ani EGiB WFS o obręb i numer. Wpisz pełny numer działki albo spróbuj za chwilę"
        ) from exc


def resolve_parcel(text: str) -> str:
    """The full identifier for what the user typed. Raises ParcelLookupError (with a list when several parcels fit)."""
    text = (text or "").strip()
    try:
        return normalize_parcel_id(text)
    except (InvalidParcelId, ValueError):
        pass
    point = parse_coordinates(text)
    if point is not None:
        return _by_point(*point)
    if _numbers(text) is not None:
        raise ParcelLookupError(
            "Współrzędne leżą poza Polską. Wpisz je jako szerokość i długość, np. 53,2705 18,1353"
        )
    m = _NAME_RE.match(text)
    if not m:
        raise ParcelLookupError(FORMAT_ERROR)
    choices = _by_name(m.group("precinct").strip(), m.group("number"))
    if len(choices) == 1:
        return choices[0].id
    raise ParcelLookupError(f"Obręb i numer pasują do {len(choices)} działek. Wybierz jedną z listy", choices)


def error_text(error: ParcelLookupError) -> str:
    """The message of a field error: the sentence, then one line "id|label" per choice (the form turns them into links)."""
    return "\n".join([error.message, *(f"{c.id}|{c.label}" for c in error.choices)])


# ------------------------------------------------------------------ the request


def parse_request(
    q: Mapping[str, str], today: date | None = None
) -> tuple[ReportRequest | None, list[FieldError]]:
    today = today or date.today()
    errors: list[FieldError] = []
    raw_id = (q.get("dzialka") or "").strip()
    parcel_id = ""
    if not raw_id:
        errors.append(FieldError(field="dzialka", message=f"Wpisz numer działki, np. {ID_HINT}"))
    else:
        try:
            parcel_id = resolve_parcel(raw_id)
        except ParcelLookupError as exc:
            errors.append(FieldError(field="dzialka", message=error_text(exc)))
        except GeodataError:
            errors.append(FieldError(field="dzialka", message=FORMAT_ERROR))
    day = None
    try:
        day = parse_date(q.get("data") or "")
    except ValueError:
        errors.append(
            FieldError(field="data", message="Wpisz datę oceny w postaci dd.mm.rrrr, np. 20.07.2023")
        )
    if day is not None and not (FIRST_DAY <= day <= today):
        errors.append(
            FieldError(
                field="data", message=f"Data musi być z ostatnich 10 lat, od 1.01.2016 do {today:%d.%m.%Y}"
            )
        )
    crop = None
    try:
        crop = CropGroup((q.get("uprawa") or "").strip())
    except ValueError:
        errors.append(FieldError(field="uprawa", message="Wybierz uprawę z listy"))
    soil = (q.get("gleba") or "").strip() or None
    if soil is not None and soil not in SOIL_CATEGORIES:
        errors.append(FieldError(field="gleba", message="Kategoria gleby to I, II, III albo IV"))
    if errors:
        return None, errors
    plan = sorted({int(p) for p in (q.get("plan") or "").split(",") if p.strip().isdigit()})
    view = "doradca" if q.get("widok") == "doradca" else "rolnik"
    return ReportRequest(
        parcel_id=parcel_id, day=day, crop=crop, view=view, plan=plan, soil_override=soil
    ), []
