"""HTTP routes: start screen, report, print view, parcel photo, section fragments, JSON API. See contracts/api.md."""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape

from app import datasource, fmt
from app.context import ReportContext
from app.drought.chart import hbar_svg
from app.drought.kbw import assess
from app.geodata import InvalidParcelId, fetch_all
from app.inputs import FORMAT_ERROR, parse_request
from app.mapview import map_view
from app.models import (
    CROP_CHOICES,
    CROP_LABELS,
    OUT_OF_SEASON,
    SECTION_ORDER,
    CropGroup,
    FieldError,
    Report,
    ReportRequest,
)
from app.picker import router as picker_router
from app.report import ParcelUnavailable, build_report, parcel_info
from app.soil import assess_soil

BASE = Path(__file__).parent
app = FastAPI(title="Bilans działki")
app.include_router(picker_router)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")
templates.env.filters.update(
    dec=fmt.dec,
    mm=fmt.mm,
    ha=fmt.ha,
    pct=fmt.pct,
    day=fmt.day,
    day_month=fmt.day_month,
    seconds=fmt.seconds,
    crop_label=lambda code: CROP_LABELS[CropGroup(code)].lower(),
)
templates.env.globals.update(hbar=hbar_svg, out_of_season=OUT_OF_SEASON)

# Example parcels on the start screen (frozen copies in demo/data/geodata, no network needed).
EXAMPLES = [
    {"dzialka": "040303_2.0002.189/13", "data": "2023-07-20", "uprawa": "zboza_jare",
     "label": "189/13, gm. Dobrcz", "note": "zboża jare, 20.07.2023"},
    {"dzialka": "100403_2.0011.144", "data": "2026-11-21", "uprawa": "rosliny_straczkowe",
     "label": "144, gm. Góra Świętej Małgorzaty", "note": "rośliny strączkowe, 21.11.2026"},
]  # fmt: skip


# What the start form holds before the user changes anything: one click on "Oceń działkę" gives a verdict.
DEFAULT_FORM = {"dzialka": "040303_2.0002.189/13", "data": "2023-07-20", "uprawa": "zboza_jare"}


def _common() -> dict:
    return {"crops": [(c.value, CROP_LABELS[c]) for c in CROP_CHOICES], "examples": EXAMPLES}


def _start(request: Request, q: dict, errors: list[FieldError], status: int = 200) -> HTMLResponse:
    ctx = _common() | {"title": "Bilans działki", "q": q, "errors": {e.field: e.message for e in errors}}
    return templates.TemplateResponse(request, "start.html", ctx, status_code=status)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    # Only a key missing from the link gets its default; a parameter the user left empty stays empty.
    return _start(request, DEFAULT_FORM | dict(request.query_params), [])


log = logging.getLogger(__name__)

# A live report that takes longer than this answers with the photo and the verdict first; the sections follow.
FAST_WAIT_S = 10.0
FIRST_LOOK_WAIT_S = 6.0  # the photo and the verdict on the waiting page may take this long
SECTION_WAIT_S = (
    20.0  # one /raport/sekcja request waits this long for the report, then asks the browser to retry
)
JOB_TTL_S = (
    3 * 60.0
)  # a waiting page needs its report for the next minute; a later reload recomputes from the disk cache
GENERIC_ERROR = "Nie udało się policzyć raportu dla tej działki. Spróbuj za chwilę albo wybierz inną datę."

_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="report")
_jobs: dict[str, tuple[float, Future[Report]]] = {}  # reports still being computed for a waiting page
_jobs_lock = threading.Lock()

# What each section waits for on the waiting page (shown as "Liczę… czekam na: …").
WAITING_FOR = {
    "historia": "pogoda z poprzednich sezonów",
    "gmina": "tabela SMSR IUNG dla gminy",
    "przyczyny": "pogoda, rzeźba terenu (NMT) i zdjęcia satelitarne",
    "retencja": "rzeźba terenu (NMT) i rowy (BDOT10k)",
    "uprawa": "bilans wody i zabiegi dla uprawy",
    "plan": "działania z sekcji 4, 5 i 7",
    "nawadnianie": "bilans wody i prognoza pogody",
    "zrodla": "odpowiedzi wszystkich źródeł",
}  # fmt: skip
SECTION_TITLES = {sid: (n, title) for sid, n, title in SECTION_ORDER}


def _report_or_errors(request: Request) -> tuple[ReportRequest | None, list[FieldError]]:
    q = dict(request.query_params)
    req, errors = parse_request(q)
    return req, errors


def _job_key(req: ReportRequest) -> str:
    return hashlib.sha1(req.model_dump_json().encode("utf-8")).hexdigest()


def _stash(req: ReportRequest, future: Future[Report]) -> None:
    now = time.monotonic()
    with _jobs_lock:
        for key in [k for k, (at, _) in _jobs.items() if now - at > JOB_TTL_S]:
            del _jobs[key]
        _jobs[_job_key(req)] = (now, future)


def _stored(req: ReportRequest) -> Future[Report] | None:
    with _jobs_lock:
        entry = _jobs.get(_job_key(req))
    return entry[1] if entry else None


def _is_live(req: ReportRequest) -> bool:
    """True when the data of this request are not a committed copy, so the report needs the network."""
    try:
        return datasource.frozen_copy(req.parcel_id, req.day) is None
    except InvalidParcelId:
        return False


def _failure(request: Request, q: dict, exc: Exception) -> HTMLResponse:
    """The start screen with the reason next to the field; an unexpected error is logged and says what to do."""
    if isinstance(exc, ParcelUnavailable):
        return _start(request, q, [FieldError(field="dzialka", message=str(exc))], status=422)
    if isinstance(exc, InvalidParcelId):
        return _start(request, q, [FieldError(field="dzialka", message=FORMAT_ERROR)], status=422)
    log.error("report failed", exc_info=exc)
    return _start(request, q, [FieldError(field="dzialka", message=GENERIC_ERROR)], status=500)


def _page_context(request: Request, q: dict, report: Report) -> dict:
    return _common() | {
        "title": f"Działka {report.parcel.number} · Bilans działki",
        "q": q,
        "report": report,
        "sections_order": SECTION_ORDER,
        "query": request.url.query,
    }


def _render_report(request: Request, template: str, *, waiting_page: bool = False) -> HTMLResponse:
    q = dict(request.query_params)
    req, errors = _report_or_errors(request)
    if req is None:
        return _start(request, q, errors, status=422)
    try:
        if waiting_page and _is_live(req):
            future = _pool.submit(build_report, req)
            try:
                report = future.result(timeout=FAST_WAIT_S)
            except FutureTimeout:
                _stash(req, future)
                return _waiting_page(request, q, req)
        else:
            report = build_report(req)
    except Exception as exc:  # noqa: BLE001 - every failure ends as a screen with a sentence, never a trace
        return _failure(request, q, exc)
    return templates.TemplateResponse(request, template, _page_context(request, q, report))


@app.get("/raport", response_class=HTMLResponse)
def report_page(request: Request) -> HTMLResponse:
    return _render_report(request, "report.html", waiting_page=True)


@app.get("/raport/druk", response_class=HTMLResponse)
def report_print(request: Request) -> HTMLResponse:
    return _render_report(request, "print.html")


# ---- the waiting page: photo and verdict first, sections as they are computed -------------------------------


def _first_look(req: ReportRequest) -> dict:
    """Photo, header and verdict from the sources that are quick (parcel, ortho, weather, soil): the same
    calls as the report's first steps, on the same cached downloads. Raises when the parcel is not available."""
    data = fetch_all(
        req.parcel_id, req.day, sources=("ortho", "weather", "soil"), budget_s=FIRST_LOOK_WAIT_S - 1,
        history_years=datasource.HISTORY_YEARS,
    )  # fmt: skip
    if data.parcel.status == "error":  # the same answer build_report gives
        raise ParcelUnavailable(f"ULDK nie zna działki {req.parcel_id}. Sprawdź numer obrębu i działki.")
    if not data.parcel.usable:
        raise TimeoutError("ULDK did not answer in time")  # the page waits for the report without the photo
    ctx = ReportContext(request=req, data=data, parcel=parcel_info(data))
    ctx.soil = assess_soil(ctx)
    w = data.weather.data if data.weather.usable else None
    verdict = assess(
        w.dates if w else [], w.precipitation_mm if w else [], w.et0_mm if w else [], req.day, req.crop,
        ctx.soil.category,
    )  # fmt: skip
    return {"parcel": ctx.parcel, "soil": ctx.soil, "map": map_view(ctx), "verdict": verdict}


def _placeholder(section_id: str, query: str, delay_ms: int = 0) -> Markup:
    """A section that is still being computed: its heading, the words "Liczę… czekam na: …" and the request
    that replaces it with the finished section."""
    n, title = SECTION_TITLES[section_id]
    trigger = f"load delay:{delay_ms}ms" if delay_ms else "load"
    return Markup(
        '<section id="{id}" aria-labelledby="h-{id}" hx-get="/raport/sekcja/{id}?{q}" '
        'hx-trigger="{trigger}" hx-swap="outerHTML"><h2 class="sec-h" id="h-{id}"><span class="n">{n}</span>{t}</h2>'
        '<p class="loading">Liczę… czekam na: <b>{w}</b></p></section>'
    ).format(
        id=section_id,
        q=escape(query),
        trigger=trigger,
        n=n,
        t=escape(title),
        w=escape(WAITING_FOR[section_id]),
    )


def _waiting_page(request: Request, q: dict, req: ReportRequest) -> HTMLResponse:
    first = None
    try:
        first = _pool.submit(_first_look, req).result(timeout=FIRST_LOOK_WAIT_S)
    except (ParcelUnavailable, InvalidParcelId) as exc:  # the answer is known: no page that waits for nothing
        return _failure(request, q, exc)
    except Exception as exc:  # noqa: BLE001 - the page still works without the early photo and verdict
        log.info("first look unavailable: %s", exc)
    query = request.url.query
    ctx = _common() | {
        "title": "Liczę raport · Bilans działki",
        "q": q,
        "req": req,
        "first": first,
        "query": query,
        "placeholders": [
            _placeholder(sid, query, delay_ms=250 * i) for i, (sid, _, _) in enumerate(SECTION_ORDER)
        ],
        "waiting_for_result": WAITING_FOR,
    }
    response = templates.TemplateResponse(request, "loading.html", ctx)
    response.headers["Cache-Control"] = "no-store"
    return response


def _wait_for_report(req: ReportRequest) -> Future[Report]:
    """The running job for this request, or a new one kept for the next poll (one computation per report)."""
    future = _stored(req)
    if future is None:
        future = _pool.submit(build_report, req)
        _stash(req, future)
    return future


def _error_fragment(section_id: str, message: str) -> HTMLResponse:
    n, title = SECTION_TITLES[section_id]
    return HTMLResponse(
        f'<section id="{section_id}" aria-labelledby="h-{section_id}"><h2 class="sec-h" id="h-{section_id}">'
        f'<span class="n">{n}</span>{escape(title)}</h2><p class="error">{escape(message)}</p></section>'
    )


def _failure_text(exc: BaseException) -> str:
    if isinstance(exc, ParcelUnavailable):
        return str(exc)
    log.error("report failed", exc_info=exc)
    return GENERIC_ERROR


@app.get("/raport/sekcja/{section_id}", response_class=HTMLResponse)
def report_section(request: Request, section_id: str) -> HTMLResponse:
    req, errors = _report_or_errors(request)
    if req is None or section_id not in SECTION_TITLES:
        return HTMLResponse('<p class="error">Nie ma takiej części raportu.</p>', status_code=404)
    future = _wait_for_report(req)
    try:
        report = future.result(timeout=SECTION_WAIT_S)
    except FutureTimeout:  # still computing: the browser asks again in 2 s (htmx swaps only 2xx answers)
        return HTMLResponse(_placeholder(section_id, request.url.query, delay_ms=2000))
    except Exception as exc:  # noqa: BLE001
        return _error_fragment(section_id, _failure_text(exc))
    return templates.TemplateResponse(
        request, f"sections/{section_id}.html", {"report": report, "s": report.section(section_id)}
    )


OOB = ' hx-swap-oob="outerHTML"'


def _out_of_band(html: str, opening: str, new_opening: str) -> str:
    """The same markup with `hx-swap-oob`: htmx puts it in place of the element that has the same id."""
    if opening not in html:
        raise ValueError(f"report template changed: {opening!r} not found")
    return html.replace(opening, new_opening, 1)


@app.get("/raport/wynik", response_class=HTMLResponse)
def report_result(request: Request) -> HTMLResponse:
    """The top of the finished report (header, verdict, summary) and the map column, to replace the early
    versions on the waiting page. Waits for the report; asks the browser to come back while it is still computing."""
    q = dict(request.query_params)
    req, errors = _report_or_errors(request)
    if req is None:
        return HTMLResponse('<p class="error">Nie ma takiego raportu.</p>', status_code=404)
    again = (
        f'<div id="wynik-trigger" hx-get="/raport/wynik?{escape(request.url.query)}" '
        'hx-trigger="load delay:2s" hx-swap="outerHTML"></div>'
    )
    try:
        report = _wait_for_report(req).result(timeout=SECTION_WAIT_S)
    except FutureTimeout:
        return HTMLResponse(again)
    except Exception as exc:  # noqa: BLE001
        return HTMLResponse(f'<p class="error">{escape(_failure_text(exc))}</p>')
    ctx = _page_context(request, q, report)

    def part(name: str) -> str:
        return templates.get_template(f"report/{name}.html").render(ctx)

    out = [
        _out_of_band(
            part("_head"), '<header class="report-head">', f'<header class="report-head" id="naglowek"{OOB}>'
        ),
        _out_of_band(
            part("_verdict"),
            '<section class="verdict" id="werdykt"',
            f'<section class="verdict" id="werdykt"{OOB}',
        ),
        _out_of_band(part("_toc"), '<nav class="toc" id="skrot"', f'<nav class="toc" id="skrot"{OOB}'),
        _out_of_band(part("_map"), '<div class="mapcol">', f'<div class="mapcol" id="mapa"{OOB}>'),
    ]
    return HTMLResponse("\n".join(out))


def _photo_data(parcel_id: str, day: date):
    """The ortho photo of the parcel: from a committed copy, else downloaded alone (not the whole report)."""
    copy = datasource.frozen_copy(parcel_id, day)
    if copy is not None:
        return copy
    return fetch_all(parcel_id, day, sources=("ortho",), budget_s=datasource.LIVE_BUDGET_S)


@app.get("/raport/zdjecie")
def parcel_photo(dzialka: str, data: str) -> Response:
    try:
        result = _photo_data(dzialka, date.fromisoformat(data))
    except (InvalidParcelId, ValueError):
        return Response(status_code=404)
    if not result.ortho.usable:
        return Response(status_code=404)
    o = result.ortho.data
    return Response(o.image, media_type=o.content_type, headers={"Cache-Control": "max-age=3600"})


@app.get("/api/uprawy")
def api_crops() -> list[dict]:
    return [{"kod": c.value, "nazwa": CROP_LABELS[c]} for c in CROP_CHOICES]


@app.get("/api/raport")
def api_report(request: Request) -> JSONResponse:
    req, errors = _report_or_errors(request)
    if req is None:
        return JSONResponse({"bledy": [e.model_dump() for e in errors]}, status_code=422)
    try:
        report = build_report(req)
    except ParcelUnavailable as exc:
        return JSONResponse({"bledy": [{"field": "dzialka", "message": str(exc)}]}, status_code=422)
    except InvalidParcelId:
        return JSONResponse({"bledy": [{"field": "dzialka", "message": FORMAT_ERROR}]}, status_code=422)
    except Exception:  # noqa: BLE001
        log.exception("report failed")
        return JSONResponse({"bledy": [{"field": "dzialka", "message": GENERIC_ERROR}]}, status_code=500)
    return JSONResponse(report.model_dump(mode="json"))
