"""The in-season forecast sentence names the analysis date it stands on."""

from datetime import date

from app.models import CropGroup, ReportRequest
from app.report import build_report


def test_forecast_sentence_starts_from_the_analysis_date() -> None:
    r = build_report(
        ReportRequest(parcel_id="040303_2.0002.189/13", day=date(2023, 7, 20), crop=CropGroup.ZBOZA_JARE)
    )
    assert r.forecast.state == "ok"
    assert r.forecast.sentence.startswith("Na dzień 20.07.2023: ")
