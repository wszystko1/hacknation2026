"""Cold-report gate, security headers and closed docs, all without network (the report builder is a mock)."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app import limits, main
from app.models import Report


class _Counter:
    def __init__(self, delay: float) -> None:
        self.delay, self.now, self.peak, self.calls = delay, 0, 0, 0
        self.lock = threading.Lock()

    def __call__(self, req) -> Report:
        with self.lock:
            self.now += 1
            self.calls += 1
            self.peak = max(self.peak, self.now)
        time.sleep(self.delay)
        with self.lock:
            self.now -= 1
        raise RuntimeError("mock: no report needed, only the concurrency")


def _fresh_app(monkeypatch, gate: limits.ColdGate, counter: _Counter):
    monkeypatch.setattr(main, "_is_live", lambda req: True)  # every parcel needs the network
    monkeypatch.setattr(main, "build_report", counter)
    monkeypatch.setattr(main.app.state, "cold_gate", gate, raising=False)
    # the app's own middleware reads the gate it was installed with: install a second app for isolation
    from fastapi import FastAPI

    app = FastAPI()
    app.get("/api/raport")(main.api_report)
    limits.install(app, gate)
    return app


def _get(client: TestClient, n: int):
    params = {"dzialka": f"040303_2.0002.{n}", "data": "20.07.2023", "uprawa": "zboza_jare"}
    return client.get("/api/raport", params=params)


def test_six_cold_reports_run_at_most_three_at_once(monkeypatch) -> None:
    counter = _Counter(0.3)
    gate = limits.ColdGate(slots=3, wait_s=10)
    client = TestClient(_fresh_app(monkeypatch, gate, counter))
    with ThreadPoolExecutor(6) as pool:
        codes = list(pool.map(lambda n: _get(client, n).status_code, range(100, 106)))
    assert counter.calls == 6
    assert counter.peak <= 3
    assert gate.peak == 3
    assert 503 not in codes  # all waited their turn
    assert gate.running == 0


def test_overflow_gets_503_with_retry_after(monkeypatch) -> None:
    counter = _Counter(0.8)
    gate = limits.ColdGate(slots=3, wait_s=0.2)
    client = TestClient(_fresh_app(monkeypatch, gate, counter))
    with ThreadPoolExecutor(6) as pool:
        responses = list(pool.map(lambda n: _get(client, n), range(200, 206)))
    busy = [r for r in responses if r.status_code == 503]
    assert len(busy) == 3
    assert counter.peak <= 3
    for r in busy:
        assert int(r.headers["Retry-After"]) > 0
        assert r.json()["detail"] == "Serwer jest zajęty, spróbuj za chwilę"
        assert r.headers["Content-Security-Policy"]
    assert gate.running == 0


def test_html_page_gets_polish_503() -> None:
    r = limits._busy("/raport")
    assert r.status_code == 503 and r.headers["Retry-After"]
    assert "Serwer jest zajęty, spróbuj za chwilę" in r.body.decode()


def test_cached_report_skips_the_gate(monkeypatch) -> None:
    counter = _Counter(0.0)
    gate = limits.ColdGate(slots=1, wait_s=0.1)
    app = _fresh_app(monkeypatch, gate, counter)
    client = TestClient(app)
    key = None

    def fake_key(query):
        nonlocal key
        from app.inputs import parse_request

        req, _ = parse_request(query)
        key = main._job_key(req)
        return req, key, True

    monkeypatch.setattr(limits, "_request_key", fake_key)
    assert gate._sem.acquire(blocking=False)  # the only slot is taken by someone else
    _get(client, 300)  # parse once to learn the key
    assert gate.running == 0
    gate.mark_warm(key)
    assert _get(client, 300).status_code != 503  # known report: no waiting for the slot
    gate._sem.release()


def test_security_headers_on_real_app() -> None:
    r = TestClient(main.app).get("/health")
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    assert "script-src 'self'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["Referrer-Policy"]
    assert "geolocation" in r.headers["Permissions-Policy"]


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_docs_closed_when_live_only(monkeypatch, path: str) -> None:
    from fastapi import FastAPI

    monkeypatch.setenv("HN_LIVE_ONLY", "1")
    app = FastAPI()
    limits.install(app)
    assert TestClient(app).get(path).status_code == 404


def test_docs_open_locally(monkeypatch) -> None:
    from fastapi import FastAPI

    monkeypatch.delenv("HN_LIVE_ONLY", raising=False)
    app = FastAPI()
    limits.install(app)
    assert TestClient(app).get("/openapi.json").status_code == 200
