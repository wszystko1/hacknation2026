"""Shared helpers of the acceptance tests: the demo parcels and a report through the public API."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.models import Report

client = TestClient(app)

DOBRCZ = {"dzialka": "040303_2.0002.189/13", "data": "2023-07-20", "uprawa": "zboza_jare"}
GSM_TODAY = {"dzialka": "100403_2.0011.144", "data": "2026-11-21", "uprawa": "rosliny_straczkowe"}


def query(params: dict, **extra: str) -> str:
    from urllib.parse import urlencode

    return urlencode(params | extra)


def report(params: dict = DOBRCZ, **extra: str) -> Report:
    r = client.get(f"/api/raport?{query(params, **extra)}")
    assert r.status_code == 200, r.text[:500]
    return Report.model_validate(r.json())


def html(params: dict = DOBRCZ, path: str = "/raport", **extra: str) -> str:
    r = client.get(f"{path}?{query(params, **extra)}")
    assert r.status_code == 200, r.text[:500]
    return r.text
