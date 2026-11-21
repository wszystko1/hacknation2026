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
) -> httpx.Response:
    """Send a request; retry 429/5xx and transport errors with exponential backoff.

    `deadline` is a time.monotonic() value after which no new attempt starts.
    Raises UpstreamError when all attempts fail; CacheMiss when offline.
    """
    if config.is_offline():
        raise CacheMiss(f"offline: network request to {url} refused")
    client = get_client()
    last = "no attempt made"
    for attempt in range(retries + 1):
        left = None if deadline is None else deadline - time.monotonic()
        if left is not None and left <= 0.05:
            break
        per_try = timeout if left is None else max(0.05, min(timeout, left))
        try:
            resp = client.request(method, url, params=params, json=json, data=data, timeout=per_try)
            if resp.status_code not in RETRY_STATUS:
                return resp
            last = f"HTTP {resp.status_code} from {url}: {resp.text[:200]}"
        except httpx.HTTPError as exc:
            last = f"{type(exc).__name__} from {url}: {exc}"
        if attempt < retries:
            time.sleep(backoff * (2**attempt))
    raise UpstreamError(last)


def get(url: str, **kwargs: Any) -> httpx.Response:
    return request("GET", url, **kwargs)
