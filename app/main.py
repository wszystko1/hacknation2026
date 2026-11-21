"""HTTP routes: start screen, report, print view, parcel photo, section fragments, JSON API. See contracts/api.md."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import datasource, fmt
from app.drought.chart import hbar_svg
from app.geodata import InvalidParcelId
from app.inputs import parse_request
from app.models import (
    CROP_CHOICES,
    CROP_LABELS,
    OUT_OF_SEASON,
    SECTION_ORDER,
    CropGroup,
    FieldError,
    ReportRequest,
)
from app.picker import router as picker_router
from app.report import ParcelUnavailable, build_report

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
    return _start(request, {}, [])


def _report_or_errors(request: Request) -> tuple[ReportRequest | None, list[FieldError]]:
    q = dict(request.query_params)
    req, errors = parse_request(q)
    return req, errors


def _render_report(request: Request, template: str) -> HTMLResponse:
    q = dict(request.query_params)
    req, errors = _report_or_errors(request)
    if req is None:
        return _start(request, q, errors, status=422)
    try:
        report = build_report(req)
    except ParcelUnavailable as exc:
        return _start(request, q, [FieldError(field="dzialka", message=str(exc))], status=422)
    ctx = _common() | {
        "title": f"Działka {report.parcel.number} · Bilans działki",
        "q": q,
        "report": report,
        "sections_order": SECTION_ORDER,
        "query": request.url.query,
    }
    return templates.TemplateResponse(request, template, ctx)


@app.get("/raport", response_class=HTMLResponse)
def report_page(request: Request) -> HTMLResponse:
    return _render_report(request, "report.html")


@app.get("/raport/druk", response_class=HTMLResponse)
def report_print(request: Request) -> HTMLResponse:
    return _render_report(request, "print.html")


@app.get("/raport/sekcja/{section_id}", response_class=HTMLResponse)
def report_section(request: Request, section_id: str) -> HTMLResponse:
    req, errors = _report_or_errors(request)
    if req is None or section_id not in {s for s, _, _ in SECTION_ORDER}:
        return HTMLResponse('<p class="error">Nie ma takiej części raportu.</p>', status_code=404)
    report = build_report(req)
    return templates.TemplateResponse(
        request, f"sections/{section_id}.html", {"report": report, "s": report.section(section_id)}
    )


@app.get("/raport/zdjecie")
def parcel_photo(dzialka: str, data: str) -> Response:
    from datetime import date

    try:
        result, _ = datasource.load(dzialka, date.fromisoformat(data))
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
    return JSONResponse(report.model_dump(mode="json"))
