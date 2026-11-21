"""K3: the chance that the balance falls below the threshold before the end of the critical period.

The app method keeps no stored weights: the balance up to the analysis date is known, the rest of the critical
period is completed with the weather of the same calendar days in each earlier season. Its accuracy comes from
a rolling validation over years (metrics.json) and stands next to the sentence in the plan section.
"""

from __future__ import annotations

import re

import pytest
from markupsafe import escape

from tests.acceptance.helpers import DOBRCZ, GSM_TODAY, html, report

PLACEHOLDER = "Tu pojawi się"


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_demo_date_gets_a_chance_from_earlier_seasons() -> None:
    # 20.07.2023, spring cereals: periods ending 31.07 and 10.08 still carry a threshold.
    f = report(DOBRCZ).forecast
    assert f.state == "ok"
    assert f.method in ("analog", "gbdt", "historical")
    assert f.k is not None and f.n is not None
    assert 0 <= f.k <= f.n
    assert f.n >= 5
    assert PLACEHOLDER not in f.sentence
    if f.method in ("analog", "historical"):
        assert f"{f.k} z {f.n}" in f.sentence


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_sentence_and_its_accuracy_stand_in_the_plan_section() -> None:
    f = report(DOBRCZ).forecast
    assert f.skill_sentence
    assert PLACEHOLDER not in f.skill_sentence
    assert re.search(r"\d", f.skill_sentence)
    page = html(DOBRCZ)
    plan = page[page.index('<section id="plan"') :]
    plan = plan[: plan.index("</section>")]
    assert str(escape(f.sentence)) in plan
    assert str(escape(f.skill_sentence)) in plan


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_date_after_the_critical_period_says_so() -> None:
    f = report(GSM_TODAY).forecast
    assert f.state == "period_over"
    assert f.probability is None
    assert f.sentence
    assert PLACEHOLDER not in f.sentence


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_crop_without_a_threshold_gets_no_chance() -> None:
    f = report(DOBRCZ | {"uprawa": "inna"}).forecast
    assert f.state == "no_threshold"
    assert f.probability is None
    assert f.sentence
    assert PLACEHOLDER not in f.sentence
