"""Server resilience: a gate for cold reports, security headers and closed API docs on the online server.

A cold report (data fetched from the network) takes 65-190 MB and dozens of threads, so only `MAX_COLD` of them
are computed at once. The rest wait up to `QUEUE_WAIT_S`, then get a Polish 503 with Retry-After. A report that is
already known (committed copy, or computed earlier in this process, so its data sit in the cache) skips the gate.
`install(app)` is the only call the app needs."""

from __future__ import annotations

import asyncio
import threading
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from concurrent.futures import Future

import anyio.to_thread
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response

MAX_COLD = 3
QUEUE_WAIT_S = 30.0
RETRY_AFTER_S = 10
BUSY_TEXT = "Serwer jest zajęty, spróbuj za chwilę"

# Pages and fragments that start or wait for a report computation.
_GATED_EXACT = {"/raport", "/raport/druk", "/raport/wynik", "/api/raport", "/raport/stan-roslin"}
_GATED_PREFIX = ("/raport/sekcja/",)

# Style and script from the app itself; the templates carry a few inline scripts and styles, hence 'unsafe-inline'.
CSP = (
    "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
    "script-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'self'; form-action 'self'; "
    "frame-ancestors 'none'"
)
SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=(), payment=(), usb=()",
}
_DOC_PATHS = {"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}


class ColdGate:
    """At most `slots` cold reports at once; a slot belongs to a report key, not to a single request."""

    def __init__(self, slots: int = MAX_COLD, wait_s: float = QUEUE_WAIT_S) -> None:
        self.wait_s = wait_s
        self._sem = threading.BoundedSemaphore(slots)
        self._lock = threading.Lock()
        self._held: set[str] = set()
        self._warm: OrderedDict[str, None] = OrderedDict()
        self.running = 0
        self.peak = 0

    def is_warm(self, key: str) -> bool:
        with self._lock:
            return key in self._warm

    def mark_warm(self, key: str) -> None:
        with self._lock:
            self._warm[key] = None
            self._warm.move_to_end(key)
            while len(self._warm) > 2000:
                self._warm.popitem(last=False)

    def holds(self, key: str) -> bool:
        with self._lock:
            return key in self._held

    async def acquire(self, key: str) -> bool:
        deadline = time.monotonic() + self.wait_s
        while not self._sem.acquire(blocking=False):
            if time.monotonic() >= deadline:
                return False
            await asyncio.sleep(0.05)
        with self._lock:
            self._held.add(key)
            self.running += 1
            self.peak = max(self.peak, self.running)
        return True

    def release(self, key: str) -> None:
        with self._lock:
            if key not in self._held:
                return
            self._held.discard(key)
            self.running -= 1
        self._sem.release()


def _busy(path: str) -> Response:
    headers = {"Retry-After": str(RETRY_AFTER_S), "Cache-Control": "no-store"}
    if path.startswith("/api"):
        return JSONResponse({"detail": BUSY_TEXT}, status_code=503, headers=headers)
    body = (
        '<!doctype html><html lang="pl"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
        f'<title>{BUSY_TEXT} · ChrońPlon</title><body style="font-family:system-ui,sans-serif;max-width:32rem;'
        f'margin:4rem auto;padding:0 1rem"><h1>{BUSY_TEXT}</h1><p class="error">Liczone są inne raporty. '
        'Odśwież stronę za kilkanaście sekund.</p><p><a href="/">Wróć na stronę główną</a></p></body></html>'
    )
    return HTMLResponse(body, status_code=503, headers=headers)


def _gated(path: str) -> bool:
    return path in _GATED_EXACT or path.startswith(_GATED_PREFIX)


def _request_key(query: dict[str, str]):
    """(request, key, needs_network) for a valid report query, else None. Imports app.main late: it imports us."""
    from app import main

    req, _errors = main.parse_request(query)
    if req is None:
        return None
    return req, main._job_key(req), main._is_live(req)


def install(app, gate: ColdGate | None = None) -> ColdGate:
    """Register the cold-report gate and the security headers; on the online server also close /docs."""
    gate = gate or ColdGate()
    app.state.cold_gate = gate

    @app.middleware("http")
    async def _limits(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        path = request.url.path
        key = None
        if _gated(path):
            try:
                found = await anyio.to_thread.run_sync(_request_key, dict(request.query_params))
            except Exception:  # noqa: BLE001 - the route itself reports a bad request
                found = None
            if found is not None and found[2] and not gate.is_warm(found[1]) and not gate.holds(found[1]):
                if not await gate.acquire(found[1]):
                    return _with_headers(_busy(path))
                key = found[1]
        try:
            response = await call_next(request)
        except BaseException:
            if key:
                gate.release(key)
            raise
        if key:
            _settle(gate, key, response, found[0] if found else None)
        return _with_headers(response)

    if _live_only():
        app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", None) not in _DOC_PATHS]
    return gate


def _settle(gate: ColdGate, key: str, response: Response, req) -> None:
    """After the response: keep the slot while a background job for this report is still running."""
    from app import main

    future: Future | None = main._stored(req) if req is not None else None
    if future is not None and not future.done():
        def _done(f: Future, key: str = key) -> None:
            if not f.cancelled() and f.exception() is None:
                gate.mark_warm(key)
            gate.release(key)

        future.add_done_callback(_done)
        return
    if response.status_code < 400:
        gate.mark_warm(key)
    gate.release(key)


def _with_headers(response: Response) -> Response:
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    return response


def _live_only() -> bool:
    from app import datasource

    return datasource.live_only()
