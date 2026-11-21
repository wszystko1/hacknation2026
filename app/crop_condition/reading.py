"""One sentence that reads the verdict and the plants together (never a number, never a change of the badge)."""

from __future__ import annotations

from app.models import CropCondition, VerdictState


def read_together(verdict_state: VerdictState, crop_condition: CropCondition) -> str:
    """The reading under the badge; "" when there is no badge or no reading to give.

    The reading is not built yet: an empty string hides the row, the plants row still states its own gap.
    """
    return ""
