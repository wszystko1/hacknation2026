"""K3: the verdict in two variants of evaporation, ET0 FAO-56 (in the verdict until the agreement measurement
decides) and the Doroszewski-Gorski formula used by SMSR IUNG (in the advisor view), with the window ending on the
last full dekad. Irrigation stays on FAO-56."""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.drought.kbw import assess
from app.models import CropGroup
from tests.acceptance.helpers import html, report


def weather(start: date, end: date, rain: float, et0: float) -> tuple[list[str], list[float], list[float]]:
    days = [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]
    return days, [rain] * len(days), [et0] * len(days)


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_running_window_ends_on_the_last_full_dekad() -> None:
    # 15 May: the last full dekad is 1-10 May, so the window is 21 March - 10 May (51 days).
    d, p, e = weather(date(2023, 3, 1), date(2023, 5, 15), rain=0.0, et0=4.0)
    v = assess(d, p, e, date(2023, 5, 15), CropGroup.ZBOZA_JARE, "I")
    assert v.state == "running"
    assert v.period is not None and v.period.days == 51
    assert v.kbw_mm == pytest.approx(-204.0)


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_report_has_both_variants_and_the_verdict_uses_fao56() -> None:
    r = report()
    assert r.verdict.et_method == "fao56"
    dg = r.verdict_dg
    assert dg is not None
    assert dg.et_method == "dg"
    assert dg.kbw_mm is not None
    assert dg.state in {"below", "above"}


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_advisor_view_shows_the_second_variant_with_its_source() -> None:
    advisor = html(widok="doradca")
    assert "Doroszewski" in advisor
    assert "2012" in advisor


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_formula_cites_its_source_with_a_page() -> None:
    code = "".join(p.read_text(encoding="utf-8") for p in Path("app/drought").rglob("*.py"))
    assert "Doroszewski" in code
    assert "2012" in code
    assert re.search(r"\bs\. ?\d+", code)


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_irrigation_stays_on_fao56() -> None:
    assert "FAO-56" in report().section("nawadnianie").how
