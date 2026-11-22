"""The plants block of the report while the satellite picture is fetched in the background.

Three states: "waiting" (a thread runs: the block says so and asks for itself again every 5 s, at most
MAX_POLLS times), "failed" (the thread ended with an error, no clean picture, or the polls ran out: the cause and a
button to try again, at most background.MAX_ATTEMPTS threads per parcel and day) and "ready" (the finished
block, which has no polling attributes, so the polling ends). The same block stands in the verdict facts of the
adviser view, in the row of the farmer screen and in the line of what the report does not count; `place` names
the three because the page has them all at once and ids are unique.
"""

from __future__ import annotations

from urllib.parse import quote

from app.models import CropCondition, ReportRequest

from . import background

MAX_POLLS = 12  # requests of one polling chain: 4 s, then every 5 s, about a minute
PLACES = ("wiersz", "werdykt", "brak")
TIMED_OUT = "pobieranie trwa dłużej niż zwykle"
LIMIT_USED = f"wykorzystano {background.MAX_ATTEMPTS} próby pobrania"


def query_of(req: ReportRequest) -> str:
    """The part of the query that names the report; the block asks for itself with it."""
    extra = f"&gleba={req.soil_override}" if req.soil_override else ""
    return (
        f"dzialka={quote(req.parcel_id, safe='')}&data={req.day.isoformat()}&uprawa={req.crop.value}{extra}"
    )


def waiting(req: ReportRequest, place: str, polls: int = 0) -> dict:
    return {
        "place": place,
        "state": "waiting",
        "query": query_of(req),
        "polls": polls,
        "delay": 4 if not polls else 5,
    }


def failed(req: ReportRequest, place: str, cause: str, *, can_retry: bool | None = None) -> dict:
    left = background.attempts_left(req.parcel_id, req.day)
    return {
        "place": place,
        "state": "failed",
        "query": query_of(req),
        "cause": cause,
        "can_retry": (left > 0) if can_retry is None else can_retry,
    }


def from_condition(cc: CropCondition, req: ReportRequest, place: str) -> dict | None:
    """The block for a finished report: "waiting" while the thread runs, "failed" after a failed thread
    (a reason of another kind, e.g. no network, stays a plain gap listed in "Nie ujęto w raporcie")."""
    if cc.state == "waiting":
        return waiting(req, place)
    cause = background.failure_cause(cc.reason) if cc.state == "missing" else None
    if cause is not None:
        return failed(req, place, cause)
    return None


def after_poll(req: ReportRequest, place: str, status: str, reason: str, polls: int) -> dict | None:
    """The answer to one poll, from the status of the thread: None means "ready"."""
    if status == "ready":
        return None
    if status == "waiting":
        if polls >= MAX_POLLS:
            return failed(
                req, place, TIMED_OUT, can_retry=True
            )  # the thread still runs: trying again keeps it
        return waiting(req, place, polls)
    cause = background.failure_cause(reason)
    if cause is None:
        return failed(req, place, reason, can_retry=False)
    if background.attempts_left(req.parcel_id, req.day) <= 0:
        return failed(req, place, f"{cause}; {LIMIT_USED}", can_retry=False)
    return failed(req, place, cause)
