"""The report route shows the measured agreement: numbers in the commune section, none of them a bare dash."""

from __future__ import annotations

import json
import re
from pathlib import Path

from tests.acceptance.helpers import DOBRCZ, html

METRICS = json.loads((Path(__file__).resolve().parents[1] / "metrics.json").read_text(encoding="utf-8"))


def test_metrics_hold_the_measured_scores_as_numbers() -> None:
    smsr = METRICS["smsr"]
    for key in ("csi", "balanced_accuracy", "pod", "far", "csi_ci_low", "csi_ci_high", "accuracy_majority"):
        assert isinstance(smsr[key], int | float), key
    assert smsr["csi_ci_low"] <= smsr["csi"] <= smsr["csi_ci_high"]
    assert smsr["balanced_accuracy_fao56"] == smsr["balanced_accuracy"]
    assert isinstance(smsr["balanced_accuracy_dg"], int | float)


def test_commune_section_of_the_report_has_a_value_in_every_score_cell() -> None:
    page = html(DOBRCZ)
    start = page.index('id="gmina"')
    section = page[start : page.index("</section>", start)]
    cells = re.findall(r"<b>([^<]*)</b><span>(CSI|POD|FAR)</span>", section)
    assert {name for _, name in cells} == {"CSI", "POD", "FAR"}
    for value, name in cells:
        assert re.fullmatch(r"\d+,\d\d", value.strip()), f"{name}: {value!r}"
    table = re.findall(r'<div class="v[^"]*"><b>([^<]*)</b>', section)
    assert len(table) == 4 and all(re.fullmatch(r"[\d\s]+", v.strip()) for v in table)
