"""Calibration curve: margin classes, the "+" share per class, the frame sentence and the advisor section."""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pytest

from app.charts.calibration import calibration_svg
from app.validation import calibration
from app.validation.agreement import agreement_frame
from tests.acceptance.helpers import DOBRCZ, html

METRICS = json.loads((Path(__file__).resolve().parents[1] / "metrics.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("margin", "key"),
    [
        (-200.0, "le_m50"), (-50.0, "le_m50"), (-49.9, "m50_m25"),
        (-25.0, "m50_m25"), (-24.9, "m25_m10"), (-10.0, "m25_m10"), (-9.9, "m10_0"),
        (-0.1, "m10_0"), (0.0, "0_10"), (9.9, "0_10"), (10.0, "10_25"), (24.9, "10_25"),
        (25.0, "25_50"), (49.9, "25_50"), (50.0, "ge_50"), (300.0, "ge_50"),
    ],
)  # fmt: skip
def test_a_value_on_a_cut_goes_to_one_class(margin: float, key: str) -> None:
    assert calibration.class_of(margin).key == key


def test_eight_classes_each_with_a_distinct_key() -> None:
    assert len(calibration.CLASSES) == 8 and len({c.key for c in calibration.CLASSES}) == 8


def test_plus_share_per_class_on_twelve_symbols() -> None:
    # margin, SMSR "+": class le_m50 2/2, m50_m25 1/2, m25_m10 0/1, m10_0 1/2, 0_10 0/2, ge_50 0/3 (one NaN left out)
    rows = [
        (-80, True), (-50, True), (-30, True), (-25, False), (-12, False), (-5, True),
        (-0.5, False), (0, False), (9, False), (60, False), (100, False), (500, False),
    ]  # fmt: skip
    margin = np.array([m for m, _ in rows] + [float("nan")], dtype=float)
    observed = np.array([o for _, o in rows] + [True])
    counts = calibration.class_counts(margin, observed)
    assert counts[:, 0].sum() == 12
    assert counts.tolist() == [[2, 2], [2, 1], [1, 0], [2, 1], [2, 0], [0, 0], [0, 0], [3, 0]]
    shares = calibration.plus_share(counts)
    assert shares[:5] == [1.0, 0.5, 0.0, 0.5, 0.0] and shares[5] is None and shares[7] == 0.0
    share, n = calibration.confirm_share(counts)
    assert (share, n) == (3 / 4, 4)


SAMPLE = {
    "smsr.csi": 0.4, "smsr.baseline_csi_climatology": 0.1,
    "smsr.calibration.fao56.le_m50.plus_share": 0.98,
    "smsr.calibration.fao56.0_10.plus_share": 0.52,
}  # fmt: skip


def test_frame_takes_the_number_from_the_class_of_the_parcel() -> None:
    a = agreement_frame(SAMPLE, -60.0)
    assert a.k_per_100 == 98 and "w 98 na 100 przypadków" in a.sentence
    assert "50 mm i więcej poniżej progu" in a.sentence


def test_frame_near_the_threshold_is_called_uncertain() -> None:
    a = agreement_frame(SAMPLE, 5.0)
    assert "niepewny" in a.sentence and "w 52 na 100" in a.sentence


def test_frame_without_the_key_says_not_measured_and_gives_no_number() -> None:
    a = agreement_frame(SAMPLE, -30.0)
    assert "nie zmierzone" in a.sentence and not re.search(r"\d", a.sentence) and a.k_per_100 is None


def test_metrics_hold_the_curve_for_both_variants_and_the_years() -> None:
    smsr = METRICS["smsr"]
    for variant in ("fao56", "dg"):
        classes = smsr["calibration"][variant]
        assert set(classes) == {c.key for c in calibration.CLASSES}
        assert all(v["n"] > 0 and 0 <= v["plus_share"] <= 1 for v in classes.values())
    assert set(smsr["by_year"]) == {str(y) for y in range(2020, 2027)}
    assert smsr["confirm_share_margin_le_minus25"] >= 0.8


def test_chart_marks_the_class_of_the_parcel() -> None:
    flat = {k: v for k, v in _flat(METRICS).items()}
    svg = calibration_svg(flat, -30.0, "krzywa")
    assert 'data-marker="m50_m25"' in svg
    assert "data-marker" not in calibration_svg(flat, None, "krzywa")
    assert calibration_svg({}, -30.0, "krzywa") == ""


def _flat(tree: dict, prefix: str = "") -> dict:
    out: dict = {}
    for k, v in tree.items():
        key = f"{prefix}.{k}" if prefix else k
        out.update(_flat(v, key) if isinstance(v, dict) else {key: v})
    return out


def test_advisor_view_has_the_curve_with_the_parcel_and_seven_years_but_the_farmer_view_none() -> None:
    page = html(DOBRCZ, widok="doradca")
    start = page.index('id="gmina"')
    section = page[start : page.index("</section>", start)]
    assert 'id="krzywa-kalibracji"' in section and "data-marker=" in section
    table = section[section.index('id="po-latach"') :]
    assert len(re.findall(r"<tr><th scope=\"row\">20\d\d</th>", table)) == 7
    farmer = html(DOBRCZ, widok="rolnik")
    # the farmer report keeps the curve only in the collapsed "Dla doradcy" row of the Wiarygodność tab
    outside = re.sub(r'<details class="b-row" id="wiersz-dla-doradcy".*?</details>', " ", farmer, flags=re.S)
    assert "data-marker" not in outside and "krzywa-kalibracji" not in outside
    assert 'id="wiersz-dla-doradcy"' in farmer and "krzywa-kalibracji" in farmer
