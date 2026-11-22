"""The action catalogue: one CSV row per action with conditions, effect range, source and confidence.

Two files share one reader: `catalog_retencja.csv` (where to hold water on the parcel) and `catalog.csv` (soil and
crop management, irrigation). Thresholds live in `cond_*` columns, metric units only, so a rule reads them here and
not from code. A number reaches the report only through `effect_text`, which needs a document, a page, a quote and an
address in the same row.

Units of the placement thresholds: `*_m` metres, `*_pct` percent of slope, `drained` "tak"/"nie". A threshold stands
either in the quote of a Polish source (CDR 2025, with its page) or the row says "propozycja zespołu" in `confidence`:
the number is ours and is to be checked with an adviser. "Lower boundary segment" in a title or sentence is the part of
the parcel outline where the fitted slope plane leaves the parcel.

Sentence templates use `str.format` fields filled from the parcel: `{area_ha}`, `{slope_pct}`, `{catchment_ha}`,
`{length_m}`, `{distance_m}`, `{n_weirs}`, `{deficit_mm}`, `{dose_mm}`, `{dose_m3}`, `{soil}`, `{place}`, `{term}`.
"""

from __future__ import annotations

import csv
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from app.models import Action, ActionGroup, CauseCode

CATALOG_FILES = ("catalog_retencja.csv", "catalog.csv")
CONFIDENCE_LEVELS = ("badanie", "opinia ekspercka", "propozycja zespołu")
GROUP_ORDER: tuple[ActionGroup, ...] = ("retencja", "uprawa", "nawadnianie")
MAX_PER_GROUP = 3
MIN_QUOTE_CHARS = 20

Confidence = Literal["badanie", "opinia ekspercka", "propozycja zespołu"]


def _number(text: str) -> float | None:
    text = text.strip().replace(",", ".")
    return float(text) if text else None


class CatalogRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    action_id: str
    group: ActionGroup
    causes: tuple[CauseCode, ...]
    conditions: dict[str, str]  # every cond_* column, name without the prefix; "" when not set
    effect_low: float | None
    effect_high: float | None
    effect_unit: str
    source_doc: str
    source_page: str
    source_quote: str
    source_url: str
    confidence: Confidence
    legal_article: str
    term: str
    farmer_alone: bool
    title: str
    sentence: str
    mechanism: str  # id from mechanisms.csv

    @field_validator("causes")
    @classmethod
    def _causes_known(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("an action without a cause is not a recommendation")
        return value

    def cond(self, name: str) -> float | None:
        """A numeric threshold, e.g. `cond("slope_min_pct")`; None when the row does not set it."""
        return _number(self.conditions.get(name, ""))

    def cond_set(self, name: str) -> tuple[str, ...]:
        """A list threshold such as `soil` = "III;IV"; empty when the row does not restrict it."""
        raw = self.conditions.get(name, "")
        return tuple(p.strip() for p in raw.split(";") if p.strip())

    def has_full_source(self) -> bool:
        """Document, page, quote of at least 20 characters and an http address: the price of a number."""
        return bool(
            self.source_doc.strip()
            and self.source_page.strip()
            and len(self.source_quote.strip()) >= MIN_QUOTE_CHARS
            and self.source_url.startswith("http")
        )


def _row(raw: dict[str, str]) -> CatalogRow:
    return CatalogRow(
        action_id=raw["action_id"].strip(),
        group=raw["group"].strip(),  # type: ignore[arg-type]
        causes=tuple(c.strip() for c in raw["causes"].split(";") if c.strip()),  # type: ignore[arg-type]
        conditions={k[len("cond_") :]: v.strip() for k, v in raw.items() if k.startswith("cond_")},
        effect_low=_number(raw["effect_low"]),
        effect_high=_number(raw["effect_high"]),
        effect_unit=raw["effect_unit"].strip(),
        source_doc=raw["source_doc"].strip(),
        source_page=raw["source_page"].strip(),
        source_quote=raw["source_quote"].strip(),
        source_url=raw["source_url"].strip(),
        confidence=raw["confidence"].strip(),  # type: ignore[arg-type]
        legal_article=raw["legal_article"].strip(),
        term=raw["term"].strip(),
        farmer_alone=raw["farmer_alone"].strip().lower() == "tak",
        title=raw["title"].strip(),
        sentence=raw["sentence"].strip(),
        mechanism=raw["mechanism"].strip(),
    )


@lru_cache(maxsize=1)
def _load(directory: Path) -> dict[str, CatalogRow]:
    rows: dict[str, CatalogRow] = {}
    for name in CATALOG_FILES:
        with (directory / name).open(encoding="utf-8", newline="") as handle:
            for raw in csv.DictReader(handle):
                row = _row(raw)
                if row.action_id in rows:
                    raise ValueError(f"duplicate action_id {row.action_id!r} in {name}")
                rows[row.action_id] = row
    return rows


def load_catalog() -> dict[str, CatalogRow]:
    """Every action by id, retention first, in file order."""
    return dict(_load(Path(__file__).parent))


def _plain(value: float) -> str:
    return f"{value:g}".replace(".", ",")


def effect_text(row: CatalogRow) -> str:
    """ "od–do jednostka (literatura)" when the row has a full source and an effect range, else "".

    A single value (both ends equal) reads "wartość jednostka (literatura)"; the unit says whether it is a ceiling.
    """
    if row.effect_low is None or row.effect_high is None or not row.effect_unit:
        return ""
    if not row.has_full_source():
        return ""
    if row.effect_low == row.effect_high:
        amount = _plain(row.effect_low)
    else:
        amount = f"{_plain(row.effect_low)}–{_plain(row.effect_high)}"
    joiner = "" if row.effect_unit.startswith("%") else " "
    return f"{amount}{joiner}{row.effect_unit} (literatura)"


def rank_actions(actions: list[Action], day: date) -> list[Action]:
    """Order within each group and keep three: more causes first, then doable from the assessment date, then alone.

    "Doable" means the action has no deadline or its deadline `due` is not before `day`. Groups come out in the
    order of the task: retention, soil and crop, irrigation.
    """
    catalog = load_catalog()

    def alone(action: Action) -> bool:
        row = catalog.get(action.id)
        return row.farmer_alone if row else False

    def key(action: Action) -> tuple[int, int, int]:
        doable = action.due is None or action.due >= day
        return (-len(action.causes), 0 if doable else 1, 0 if alone(action) else 1)

    ranked: list[Action] = []
    for group in GROUP_ORDER:
        members = sorted((a for a in actions if a.group == group), key=key)
        ranked += members[:MAX_PER_GROUP]
    return ranked
