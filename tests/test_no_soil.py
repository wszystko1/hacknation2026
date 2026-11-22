"""Without a soil category the irrigation section shows no empty numbers and says the dose is not computed."""

from __future__ import annotations

import re
from datetime import date

from app.geodata import parcel_use
from app.models import ReportRequest, SoilInfo
from app.report import build_context
from app.sections import nawadnianie

EMPTY = re.compile(r"około\s+mm|\s0\s*m³|\(\s*m³")


def test_no_soil_section_has_no_empty_dose() -> None:
    ctx = build_context(
        ReportRequest.model_validate(
            {"parcel_id": "100403_2.0011.144", "day": date(2026, 11, 21), "crop": "rosliny_straczkowe"}
        )
    )
    ctx.soil = SoilInfo(category=None, source="brak", words="Brak: kategorii gleby")
    from app.drought.variants import main_verdict

    ctx.verdict, _ = main_verdict(ctx)
    section = nawadnianie.build(ctx)
    assert section.state == "ready"
    assert nawadnianie.NO_SOIL in section.sentences
    texts = [*section.sentences, *(f"{a.title} {a.sentence}" for a in section.actions)]
    assert not any(EMPTY.search(t) for t in texts), texts
    assert parcel_use is not None
