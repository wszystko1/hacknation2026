"""/raport/wynik answers 200 with the finished head of the report for a parcel that has no committed copy."""

from __future__ import annotations

import dataclasses
from datetime import date

from fastapi.testclient import TestClient

from app import datasource, main
from app.main import app

client = TestClient(app)
QUERY = "dzialka=040303_2.0002.189/14&data=2023-07-20&uprawa=zboza_jare"


def test_result_for_a_parcel_outside_the_copies(monkeypatch) -> None:
    sample = datasource.frozen_copy("040303_2.0002.189/13", date(2023, 7, 20))
    assert sample is not None
    parcel = dataclasses.replace(sample.parcel.data, id="040303_2.0002.189/14", number="189/14")
    other = dataclasses.replace(sample, parcel=dataclasses.replace(sample.parcel, data=parcel))
    monkeypatch.setattr(datasource, "load", lambda pid, day, **kw: (other, None))
    main._jobs.clear()
    r = client.get(f"/raport/wynik?{QUERY}")
    assert r.status_code == 200
    assert 'id="werdykt"' in r.text and 'id="naglowek"' in r.text and 'id="mapa"' in r.text
    assert "wynik-trigger" not in r.text  # the finished report, not "come back in 2 s"
