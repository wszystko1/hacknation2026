"""One sentence that reads the verdict and the plants together (never a number, never a change of the badge)."""

from __future__ import annotations

from app.models import CropCondition, VerdictState

_READINGS = {
    ("below", "weaker"): "Susza potwierdzona przez stan roślin.",
    ("below", "normal"): "Bilans poniżej progu; satelita jeszcze nie pokazuje stresu (wskaźnik reaguje z opóźnieniem).",
    ("above", "weaker"): (
        "Spadek niewyjaśniony bilansem, sprawdź na polu "
        "(lokalny opad nawalny, zalanie, zbiór lub pokos, inna uprawa)."
    ),
    ("above", "normal"): "Brak oznak problemu z wodą.",
}


def read_together(verdict_state: VerdictState, crop_condition: CropCondition) -> str:
    """The reading under the badge; "" when there is no badge.

    Without a usable picture (missing, waiting, after harvest or mowing) it states the verdict alone and what
    is missing, so a gap is never read as "plants are fine".
    """
    if verdict_state not in ("below", "above"):
        return ""
    signal = crop_condition.signal
    if crop_condition.state == "ok" and not crop_condition.harvest and signal is not None:
        return _READINGS[(verdict_state, signal)]
    if crop_condition.harvest:
        return f"Sam bilans; {crop_condition.words}."
    return "Sam bilans; brak oceny roślin."
