"""The second variant of the verdict: evaporation by the Doroszewski-Górski formula, shown in the advisor view."""

from __future__ import annotations

from app.context import ReportContext
from app.models import Verdict


def verdict_dg(ctx: ReportContext) -> Verdict | None:
    """The verdict recomputed with `et_method="dg"`; None while the formula is not wired in."""
    return None
