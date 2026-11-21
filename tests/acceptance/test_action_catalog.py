"""K1, K3: the action catalogue in CSV carries a source with a verbatim quote and a confidence level for every row.

A number (the effect of an action) reaches the report only when its row has a document, a page, a quote and an
address; effects are ranges from the literature and the report labels them as such.

Thresholds (the cond_* columns) come from Polish sources, first the CDR 2025 guide, with a page and a quote that states
the number; a row whose thresholds have no such source says "propozycja zespołu" in its confidence column. No row
rests on ACPF.
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


POLISH_SOURCES = ("CDR", "IUNG", "ODR", "Dz.U.", "Prawo wodne")


def _numbers(text: str) -> set[float]:
    return {float(n.replace(",", ".")) for n in re.findall(r"\d+(?:[.,]\d+)?", text)}


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_thresholds_have_a_polish_source_stating_them_or_are_team_proposals() -> None:
    for path in CATALOGUES:
        header = next(csv.reader(path.open(encoding="utf-8")))
        imperial = [h for h in header if re.search(r"_(ft|feet|ac|acre|acres|in|inch|inches)$", h)]
        assert not imperial, (path, imperial)
    rows = _rows()
    assert rows, "no action catalogue in app/advice/catalog*.csv"
    for r in rows:
        assert "ACPF" not in " ".join((r["source_doc"], r["source_url"], r["source_quote"])), r["action_id"]
        thresholds = {
            k: float(v.replace(",", "."))
            for k, v in r.items()
            if k.startswith("cond_") and re.fullmatch(r"-?\d+(?:[.,]\d+)?", (v or "").strip())
        }
        if not thresholds or r["confidence"] == "propozycja zespołu":
            continue
        assert any(src in r["source_doc"] for src in POLISH_SOURCES), (r["action_id"], r["source_doc"])
        assert re.search(r"\d", r["source_page"]), (r["action_id"], "page of the source")
        missing = {k: v for k, v in thresholds.items() if v not in _numbers(r["source_quote"])}
        assert not missing, (
            r["action_id"],
            "a threshold the quote does not state is a team proposal",
            missing,
        )
