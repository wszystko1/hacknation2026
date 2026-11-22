"""Shared HTTP client: connection pooling, retries with backoff on 429/5xx, generic User-Agent."""

from __future__ import annotations

import threading
import time
from typing import Any

import httpx

from . import config
from .errors import CacheMiss, UpstreamError

_lock = threading.Lock()
_client: httpx.Client | None = None

RETRY_STATUS = {429, 500, 502, 503, 504}

# Per-host breaker: a host that timed out or refused the connection is skipped for HOST_FAILURE_TTL_S, so the
# next reports do not each wait 7-12 s for a service that is down.
_failed_hosts: dict[str, float] = {}


def _host(url: str) -> str:
    return httpx.URL(url).host


def host_blocked(url: str) -> bool:
    """True while the host of `url` is in its failure window."""
    host = _host(url)
    with _lock:
        until = _failed_hosts.get(host)
        if until is None:
            return False
        if time.monotonic() >= until:
            del _failed_hosts[host]
            return False
        return True


def reset_host_failures() -> None:
    with _lock:
        _failed_hosts.clear()


def get_client() -> httpx.Client:
    """One process-wide client (httpx.Client is thread-safe)."""
    global _client
    with _lock:
        if _client is None:
            _client = httpx.Client(
                headers={"User-Agent": config.USER_AGENT},
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
                follow_redirects=True,
                timeout=httpx.Timeout(10.0, connect=5.0),
            )
        return _client


def set_client(client: httpx.Client | None) -> None:
    """Replace the shared client (tests inject httpx.MockTransport here)."""
    global _client
    with _lock:
        _client = client
    from . import uldk_guard

    reset_host_failures()
    uldk_guard.reset()  # a new client is a new network: the breaker of the old one does not apply


def request(
    method: str,
    url: str,
    *,
    params: Any = None,
    json: Any = None,
    data: Any = None,
    timeout: float = 10.0,
    retries: int = 2,
    backoff: float = 0.4,
    deadline: float | None = None,
    breaker: bool = True,
) -> httpx.Response:
    """Send a request; retry 429/5xx and transport errors with exponential backoff.

    `deadline` is a time.monotonic() value after which no new attempt starts.
    Raises UpstreamError when all attempts fail; CacheMiss when offline.
    """
    if config.is_offline():
        raise CacheMiss(f"offline: network request to {url} refused")
    if breaker and host_blocked(url):
        raise UpstreamError(f"{_host(url)} did not answer in the last {config.HOST_FAILURE_TTL_S:.0f} s: skipped")
    client = get_client()
    last = "no attempt made"
    transport_failure = False
    for attempt in range(retries + 1):
        left = None if deadline is None else deadline - time.monotonic()
        if left is not None and left <= 0.05:
            break
        per_try = timeout if left is None else max(0.05, min(timeout, left))
        try:
            resp = client.request(method, url, params=params, json=json, data=data, timeout=per_try)
            if resp.status_code not in RETRY_STATUS:
                if breaker:
                    with _lock:
                        _failed_hosts.pop(_host(url), None)
                return resp
            transport_failure = False
            last = f"HTTP {resp.status_code} from {url}: {resp.text[:200]}"
        except httpx.HTTPError as exc:
            last = f"{type(exc).__name__} from {url}: {exc}"
            transport_failure = True
        if attempt < retries:
            time.sleep(backoff * (2**attempt))
    if breaker and transport_failure:
        with _lock:
            _failed_hosts[_host(url)] = time.monotonic() + config.HOST_FAILURE_TTL_S
    raise UpstreamError(last)


def get(url: str, **kwargs: Any) -> httpx.Response:
    return request("GET", url, **kwargs)
