"""Geodata cache size cap and the per-host breaker for services that do not answer."""

import time

import httpx
import pytest

from app.geodata import cache, http
from app.geodata.errors import UpstreamError


def test_geodata_cache_pruned_on_write(tmp_path, monkeypatch):
    monkeypatch.setenv("GEODATA_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr("app.geodata.config.GEODATA_CACHE_MAX_BYTES", 1000)
    monkeypatch.setattr(cache, "_PRUNE_EVERY", 1)
    monkeypatch.setattr(cache, "_writes", 0)
    for i in range(20):
        cache.put_bytes("ns", f"k{i}", b"x" * 200)
    total = sum(p.stat().st_size for p in tmp_path.rglob("*") if p.is_file())
    assert total <= 1000 + 200  # the file written after the last prune may still be there


def test_dead_host_is_skipped_by_next_request(monkeypatch):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        raise httpx.ConnectTimeout("down", request=request)

    http.set_client(httpx.Client(transport=httpx.MockTransport(handler)))
    try:
        with pytest.raises(UpstreamError):
            http.get("https://dead.example/a", retries=1, backoff=0.0)
        first = len(calls)
        assert first == 2
        start = time.monotonic()
        with pytest.raises(UpstreamError):
            http.get("https://dead.example/b", retries=1, backoff=0.0)
        assert len(calls) == first  # no new attempt
        assert time.monotonic() - start < 0.1
        # another host is unaffected
        with pytest.raises(UpstreamError):
            http.get("https://other.example/", retries=0)
        assert len(calls) == first + 1
        # the window expires
        monkeypatch.setattr("app.geodata.config.HOST_FAILURE_TTL_S", 0.0)
        http.reset_host_failures()
    finally:
        http.set_client(None)


def test_success_clears_failure(monkeypatch):
    state = {"fail": True}

    def handler(request: httpx.Request) -> httpx.Response:
        if state["fail"]:
            raise httpx.ReadTimeout("slow", request=request)
        return httpx.Response(200, text="ok")

    http.set_client(httpx.Client(transport=httpx.MockTransport(handler)))
    try:
        with pytest.raises(UpstreamError):
            http.get("https://flaky.example/", retries=0)
        assert http.host_blocked("https://flaky.example/")
        http.reset_host_failures()
        state["fail"] = False
        assert http.get("https://flaky.example/").status_code == 200
        assert not http.host_blocked("https://flaky.example/")
    finally:
        http.set_client(None)
