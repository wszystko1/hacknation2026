"""The sources table says where the parcel outline came from."""

from __future__ import annotations

import dataclasses
from datetime import date

import pytest

from app.models import CropGroup, ReportRequest
from app.report import build_context
from app.sources_table import source_rows


def _context():
    return build_context(
        ReportRequest(parcel_id="040303_2.0002.189/13", day=date(2023, 7, 20), crop=CropGroup.ZBOZA_JARE)
    )


def _outline_row(ctx):
    rows = [r for r in source_rows(ctx) if r.label == "Obrys działki"]
    assert len(rows) == 1
    return rows[0]


def test_the_demo_parcel_has_a_row_from_the_local_copy() -> None:
    row = _outline_row(_context())
    assert row.provider == "kopia lokalna"


@pytest.mark.parametrize(("source", "provider"), [("EGiB WFS", "EGiB WFS GUGiK"), ("ULDK", "ULDK GUGiK")])
def test_an_outline_from_a_service_names_the_service(source: str, provider: str) -> None:
    ctx = _context()
    parcel = dataclasses.replace(ctx.data.parcel.data, outline_source=source)
    ctx.data = dataclasses.replace(ctx.data, parcel=dataclasses.replace(ctx.data.parcel, data=parcel))
    assert _outline_row(ctx).provider == provider
