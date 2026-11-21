"""Diagnosis of the causes of the water deficit from the parcel's data. No causes, no recommendations."""

from __future__ import annotations

from app.context import ReportContext
from app.models import Cause, Diagnosis


def diagnose(ctx: ReportContext) -> Diagnosis:
    """Skeleton: one cause from the verdict's period; the comparison with usual seasons comes next."""
    v = ctx.verdict
    if v is None or v.period is None or v.state == "no_data":
        return Diagnosis()
    p = v.period
    return Diagnosis(
        causes=[
            Cause(
                code="malo_opadu",
                words=f"spadło {p.precip_mm:.0f} mm, parowanie zabrało {p.et0_mm:.0f} mm",
                strength_mm=p.kbw_mm,
            )
        ]
    )
