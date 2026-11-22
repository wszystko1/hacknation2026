"""The one door to ULDK: refuses the decoy the demo room's network may put in its place.

The decoy (`integracja01.gugik.gov.pl/resp/uldk.php`) answers a redirect with `Content-Length` of 4 GiB, `text/html`,
`Content-Disposition: attachment` and an endless hex stream. A real ULDK answer is a few hundred bytes of
`text/plain`: a status line, then one line per parcel with fields separated by "|". We follow no redirect, accept
only that host, read as a stream with a size and time limit, and check the shape of the answer. After the first
decoy ULDK is skipped for five minutes so the next lookups go straight to the fallback.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from . import config, http
from .errors import CacheMiss, UpstreamError

ALLOWED_HOST = "uldk.gugik.gov.pl"
MAX_BYTES = 2 * 1024 * 1024
TIMEOUT_S = 3.5
TOTAL_S = 4.0
BREAKER_S = 300.0
GEOMETRY_PREFIXES = ("SRID=2180;POLYGON", "SRID=2180;MULTIPOLYGON")
MIN_FIELDS_WITH_GEOMETRY = 7
MIN_FIELDS_NAMES = 6

_lock = threading.Lock()
_clock: Callable[[], float] = time.monotonic
_tripped_until: float | None = None


class UldkDecoy(UpstreamError):
    """The answer is not from ULDK (redirect, other host, wrong type, wrong shape, too long)."""


class UldkSkipped(UpstreamError):
    """ULDK is skipped: a decoy answered less than five minutes ago."""


@dataclass(frozen=True)
class UldkAnswer:
    text: str
    url: str


def set_clock(clock: Callable[[], float] | None) -> None:
    """Replace the clock of the breaker (tests); None restores time.monotonic."""
    global _clock
    _clock = clock or time.monotonic


def reset() -> None:
    """Close the breaker."""
    global _tripped_until
    with _lock:
        _tripped_until = None


def breaker_open() -> bool:
    with _lock:
        return _tripped_until is not None and _clock() < _tripped_until


def _trip(reason: str) -> UldkDecoy:
    global _tripped_until
    with _lock:
        _tripped_until = _clock() + BREAKER_S
    return UldkDecoy(f"ULDK: answer rejected ({reason}); skipping ULDK for {int(BREAKER_S // 60)} min")


def _read(resp: httpx.Response, stop_at: float) -> bytes:
    declared = resp.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BYTES:
        raise _trip(f"declared length {declared} bytes")
    body = bytearray()
    for chunk in resp.iter_bytes():
        body += chunk
        if len(body) > MAX_BYTES:
            raise _trip("more than 2 MB")
        if time.monotonic() > stop_at:
            raise UpstreamError("ULDK: the answer took too long")
    return bytes(body)


def _check_shape(text: str, geometry: bool) -> None:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines or len(lines[0]) > 200:
        raise _trip("no status line")
    if lines[0].strip() != "0":
        return  # a status of an error ("-1 brak wyników"): the parser turns it into ParcelNotFound
    if len(lines) < 2:
        raise _trip("no data line")
    for line in lines[1:]:
        parts = line.split("|")
        if len(parts) < (MIN_FIELDS_WITH_GEOMETRY if geometry else MIN_FIELDS_NAMES):
            raise _trip("data line without fields")
        if geometry and not parts[6].startswith(GEOMETRY_PREFIXES):
            raise _trip("geometry is not SRID=2180 POLYGON")


def fetch(params: dict[str, str], *, geometry: bool, deadline: float | None = None) -> UldkAnswer:
    """GET to ULDK with the guards. Raises UldkDecoy, UldkSkipped, UpstreamError or CacheMiss."""
    if config.is_offline():
        raise CacheMiss("offline: ULDK request refused")
    url = config.ULDK_URL
    if urlsplit(url).hostname != ALLOWED_HOST:
        raise UpstreamError(f"ULDK: host {urlsplit(url).hostname} is not {ALLOWED_HOST}")
    if breaker_open():
        raise UldkSkipped("ULDK: skipped after a decoy answer")
    started = time.monotonic()
    stop_at = started + TOTAL_S
    if deadline is not None:
        stop_at = min(stop_at, deadline)
    if stop_at - started <= 0.05:
        raise UpstreamError("ULDK: no time left")
    timeout = max(0.05, min(TIMEOUT_S, stop_at - started))
    client = http.get_client()
    try:
        request = client.build_request("GET", url, params=params, timeout=timeout)
        resp = client.send(request, stream=True, follow_redirects=False)
    except httpx.HTTPError as exc:
        raise UpstreamError(f"ULDK: {type(exc).__name__}: {exc}") from exc
    try:
        if 300 <= resp.status_code < 400:
            raise _trip(f"redirect {resp.status_code}")
        if resp.url.host != ALLOWED_HOST:
            raise _trip(f"host {resp.url.host}")
        if resp.status_code != 200:
            raise UpstreamError(f"ULDK HTTP {resp.status_code}")
        if not resp.headers.get("content-type", "").lower().startswith("text/plain"):
            raise _trip(f"content type {resp.headers.get('content-type', 'none')}")
        if "attachment" in resp.headers.get("content-disposition", "").lower():
            raise _trip("content disposition attachment")
        try:
            raw = _read(resp, stop_at)
        except httpx.HTTPError as exc:
            raise UpstreamError(f"ULDK: {type(exc).__name__}: {exc}") from exc
        final_url = str(resp.url)
    finally:
        resp.close()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise _trip("not UTF-8 text") from None
    _check_shape(text, geometry)
    return UldkAnswer(text=text, url=final_url)
