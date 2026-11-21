"""The action catalogue: 11 retention rows, 15 soil, crop and irrigation rows, the ranking and the effect text."""

from __future__ import annotations

import csv
import re
from datetime import date
from pathlib import Path
from typing import get_args

from app.advice.catalog import CatalogRow, effect_text, load_catalog, rank_actions
from app.models import Action, CauseCode

ADVICE = Path("app/advice")
DAY = date(2026, 7, 10)


def _read(name: str) -> list[dict[str, str]]:
    with (ADVICE / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_file_sizes_and_groups() -> None:
    retention, field = _read("catalog_retencja.csv"), _read("catalog.csv")
    assert len(retention) == 11
    assert len(field) == 15
    assert {r["group"] for r in retention} == {"retencja"}
    assert {r["group"] for r in field} == {"uprawa", "nawadnianie"}
    assert sum(r["group"] == "nawadnianie" for r in field) == 4


def test_every_row_has_causes_from_the_cause_codes_and_a_source_document() -> None:
    codes = set(get_args(CauseCode))
    for r in _read("catalog_retencja.csv") + _read("catalog.csv"):
        causes = [c for c in r["causes"].split(";") if c]
        assert causes and set(causes) <= codes, r["action_id"]
        assert r["source_doc"].strip(), r["action_id"]
        assert r["title"].strip() and r["sentence"].strip(), r["action_id"]
        assert r["farmer_alone"] in {"tak", "nie"}, r["action_id"]


def test_ids_are_unique_and_include_those_with_a_water_law_formality() -> None:
    catalog = load_catalog()
    assert len(catalog) == 26
    for action_id in (
        "zastawka-istniejaca",
        "zastawka-nowa",
        "dreny-regulowany-odplyw",
        "przebudowa-rowu",
        "niecka-przy-wyplywie",
        "pobor-wody-nawadnianie",
    ):
        assert action_id in catalog, action_id
    assert all(re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", i) for i in catalog)


def test_no_imperial_units_in_any_column() -> None:
    for name in ("catalog_retencja.csv", "catalog.csv"):
        header = next(csv.reader((ADVICE / name).open(encoding="utf-8")))
        assert not [h for h in header if re.search(r"(^|_)(ft|feet|ac|acre|acres|in|inch|inches)(_|$)", h)], (
            name
        )


def test_placement_thresholds_read_through_the_catalogue() -> None:
    catalog = load_catalog()
    strip = catalog["pas-trawy-przy-wyplywie"]
    assert (strip.cond("slope_min_pct"), strip.cond("ditch_max_m")) == (0.5, 30)
    for action_id in ("zastawka-istniejaca", "zastawka-nowa"):
        assert catalog[action_id].cond("ditch_max_m") == 30, action_id
    tillage = catalog["uprawa-w-poprzek-stoku"]
    assert (tillage.cond("slope_min_pct"), tillage.cond("slope_max_pct")) == (4, 15)
    assert catalog["niecka-przy-wyplywie"].cond("depression_min_m") == 0.2
    assert catalog["dreny-regulowany-odplyw"].cond("slope_max_pct") == 1
    assert catalog["dreny-regulowany-odplyw"].cond("nothing") is None
    assert catalog["gleboszowanie"].cond_set("soil") == ("III", "IV")
    assert catalog["mulczowanie"].cond_set("soil") == ()


def test_the_two_actions_that_replaced_the_rows_of_a_foreign_method_are_sourced_from_cdr() -> None:
    catalog = load_catalog()
    assert "row-zadarniony" not in catalog and "pas-konturowy" not in catalog
    for action_id in ("pas-buforowy-wzdluz-rowu", "miedza-w-poprzek-stoku"):
        row = catalog[action_id]
        assert row.group == "retencja"
        assert "CDR" in row.source_doc and row.has_full_source(), action_id


def test_no_row_names_acpf_in_any_column() -> None:
    for name in ("catalog_retencja.csv", "catalog.csv"):
        assert "acpf" not in (ADVICE / name).read_text(encoding="utf-8").lower(), name
    assert "acpf" not in (ADVICE / "catalog.py").read_text(encoding="utf-8").lower()


def test_a_threshold_is_in_its_quote_or_the_row_is_a_team_proposal() -> None:
    """The row's confidence is the confidence of its numbers: a number the quote does not state is ours."""
    for row in load_catalog().values():
        numbers = {n.replace(",", ".") for n in re.findall(r"\d+(?:[.,]\d+)?", row.source_quote)}
        numeric = {
            k: v for k, v in row.conditions.items() if re.fullmatch(r"-?\d+(?:[.,]\d+)?", v.replace(",", "."))
        }
        if not numeric or row.confidence == "propozycja zespołu":
            continue
        for name, value in numeric.items():
            assert f"{float(value.replace(',', '.')):g}" in {f"{float(n):g}" for n in numbers}, (
                row.action_id,
                name,
            )
        assert row.source_page.isdigit(), row.action_id


def test_drained_outflow_row_states_the_one_percent_slope_in_its_quote() -> None:
    row = load_catalog()["dreny-regulowany-odplyw"]
    assert row.source_page == "120" and "1%" in row.source_quote
    assert row.confidence != "propozycja zespołu"


def test_effects_only_with_a_full_source() -> None:
    catalog = load_catalog()
    with_effect = [r for r in catalog.values() if r.effect_low is not None]
    assert with_effect
    for row in with_effect:
        assert row.effect_high is not None and row.effect_low <= row.effect_high, row.action_id
        assert row.has_full_source(), row.action_id
        assert effect_text(row).endswith("(literatura)"), row.action_id


def _row(**changes: object) -> CatalogRow:
    base = load_catalog()["mulczowanie"]
    return base.model_copy(update=changes)


def test_effect_text_needs_document_page_quote_and_address() -> None:
    assert effect_text(_row()) == "60% mniej parowania z gleby, największa wartość z badań (literatura)"
    assert effect_text(_row(source_doc="")) == ""
    assert effect_text(_row(source_page="")) == ""
    assert effect_text(_row(source_quote="za krótki cytat")) == ""
    assert effect_text(_row(source_url="woda.cdr.gov.pl")) == ""
    assert effect_text(_row(effect_low=None, effect_high=None)) == ""
    assert effect_text(_row(effect_unit="")) == ""


def test_effect_text_range_uses_a_decimal_comma() -> None:
    text = effect_text(_row(effect_low=1.5, effect_high=4, effect_unit="mm"))
    assert text == "1,5–4 mm (literatura)"


def _action(action_id: str, group: str, causes: int, due: date | None = None) -> Action:
    return Action(
        id=action_id,
        n=0,
        group=group,  # type: ignore[arg-type]
        title=action_id,
        sentence="",
        cause="c",
        causes=[f"przyczyna {i}" for i in range(causes)],
        when="",
        due=due,
        source="",
    )


def test_rank_puts_more_causes_first() -> None:
    ranked = rank_actions(
        [_action("pas-konturowy", "retencja", 1), _action("zastawka-nowa", "retencja", 3)], DAY
    )
    assert [a.id for a in ranked] == ["zastawka-nowa", "pas-konturowy"]


def test_rank_on_equal_causes_puts_doable_before_overdue_then_farmer_alone() -> None:
    late, ok = date(2026, 7, 1), date(2026, 8, 1)
    # mulczowanie: farmer alone; gleboszowanie: not alone
    ranked = rank_actions(
        [
            _action("gleboszowanie", "uprawa", 2, due=ok),
            _action("mulczowanie", "uprawa", 2, due=late),
            _action("miedzyplon", "uprawa", 2, due=ok),
        ],
        DAY,
    )
    assert [a.id for a in ranked] == ["miedzyplon", "gleboszowanie", "mulczowanie"]


def test_rank_keeps_three_per_group_and_orders_groups() -> None:
    actions = [_action(f"x{i}", "uprawa", 1) for i in range(5)]
    actions += [
        _action("nawadnianie-uzupelniajace", "nawadnianie", 1),
        _action("zastawka-nowa", "retencja", 1),
    ]
    ranked = rank_actions(actions, DAY)
    assert [a.group for a in ranked] == ["retencja", "uprawa", "uprawa", "uprawa", "nawadnianie"]


def test_rank_without_a_deadline_counts_as_doable() -> None:
    ranked = rank_actions(
        [_action("mulczowanie", "uprawa", 1, due=date(2026, 1, 1)), _action("miedzyplon", "uprawa", 1)], DAY
    )
    assert [a.id for a in ranked] == ["miedzyplon", "mulczowanie"]
