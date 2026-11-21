"""K1, K3: the action catalogue in CSV carries a source with a verbatim quote and a confidence level for every row.

A number (the effect of an action) reaches the report only when its row has a document, a page, a quote and an
address; effects are ranges from the literature and the report labels them as such.

Placement thresholds come from the ACPF manual v7.0 (USDA ARS, 2025), converted to metric units, each row with the
manual's page; we cite the method and copy none of its text, so ACPF rows carry no quote.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import pytest

from tests.acceptance.helpers import DOBRCZ, GSM_TODAY, report

CATALOGUES = sorted(Path("app/advice").glob("catalog*.csv"))
COLUMNS = {
    "action_id",
    "group",
    "causes",
    "effect_low",
    "effect_high",
    "effect_unit",
    "source_doc",
    "source_page",
    "source_quote",
    "source_url",
    "confidence",
    "legal_article",
    "term",
}
CONFIDENCE = {"badanie", "opinia ekspercka", "propozycja zespołu"}
GROUPS = {"retencja", "uprawa", "nawadnianie"}


def _rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in CATALOGUES:
        rows += list(csv.DictReader(path.open(encoding="utf-8")))
    return rows


def _has_full_source(r: dict[str, str]) -> bool:
    return bool(
        r["source_doc"].strip()
        and r["source_page"].strip()
        and len(r["source_quote"].strip()) >= 20
        and r["source_url"].startswith("http")
    )


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_catalogue_columns_groups_and_confidence() -> None:
    assert CATALOGUES
    for path in CATALOGUES:
        header = set(next(csv.reader(path.open(encoding="utf-8"))))
        assert COLUMNS <= header, (path, COLUMNS - header)
        assert any(h.startswith("cond_") for h in header), (
            f"{path}: thresholds go in their own cond_* columns"
        )
    rows = _rows()
    assert len(rows) >= 20
    for r in rows:
        assert r["group"] in GROUPS, r["action_id"]
        assert r["confidence"] in CONFIDENCE, r["action_id"]
        assert r["causes"].strip(), r["action_id"]


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_effect_numbers_only_with_document_page_quote_and_address() -> None:
    rows = _rows()
    assert rows, "no action catalogue in app/advice/catalog*.csv"
    for r in rows:
        low, high = r["effect_low"].strip(), r["effect_high"].strip()
        assert bool(low) == bool(high), (r["action_id"], "an effect is a range: both ends or none")
        if low:
            assert float(low) <= float(high), r["action_id"]
            assert r["effect_unit"].strip(), r["action_id"]
            assert _has_full_source(r), r["action_id"]


@pytest.mark.xfail(reason="not built yet", strict=False)
@pytest.mark.parametrize("params", [DOBRCZ, GSM_TODAY], ids=["dobrcz", "gsm-today"])
def test_report_effects_are_literature_ranges_with_a_sourced_row(params: dict) -> None:
    rows = {r["action_id"]: r for r in _rows()}
    for a in report(params).actions:
        assert a.id in rows, a.id
        effect = getattr(a, "effect", "")
        if effect:
            assert "literatur" in effect, (a.id, effect)
            assert _has_full_source(rows[a.id]), a.id


# action id -> {cond column: (lowest allowed, highest allowed)}, thresholds of the ACPF manual in metric units
ACPF_THRESHOLDS = {
    "row-zadarniony": {"cond_spi_min": (None, None), "cond_length_min_m": (50.0, 50.0)},
    "pas-konturowy": {"cond_slope_min_pct": (4.0, 4.0), "cond_slope_max_pct": (15.0, 15.0)},
    "dreny-regulowany-odplyw": {"cond_slope_max_pct": (None, 1.0)},
}


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_acpf_placement_thresholds_are_metric_with_a_manual_page_and_no_copied_text() -> None:
    rows = {r["action_id"]: r for r in _rows()}
    for path in CATALOGUES:
        header = next(csv.reader(path.open(encoding="utf-8")))
        imperial = [h for h in header if re.search(r"_(ft|feet|ac|acre|acres|in|inch|inches)$", h)]
        assert not imperial, (path, imperial)
    for action_id, conds in ACPF_THRESHOLDS.items():
        assert action_id in rows, action_id
        r = rows[action_id]
        assert "ACPF" in r["source_doc"], (action_id, r["source_doc"])
        assert re.search(r"\d", r["source_page"]), (action_id, "page of the ACPF manual")
        assert not r["source_quote"].strip(), (action_id, "we cite ACPF, we do not copy its text")
        for col, (low, high) in conds.items():
            value = float(r[col].replace(",", "."))
            assert low is None or value >= low, (action_id, col, value)
            assert high is None or value <= high, (action_id, col, value)
