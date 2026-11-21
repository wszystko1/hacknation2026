"""K2, K4: the farmer reads accuracy, balanced accuracy, recall and precision for drought, each next to the score
of the trivial answer ("zawsze częstsza odpowiedź"); CSI, POD, FAR, Peirce, Brier and BSS stay in the advisor view
and the README, each explained in one sentence."""

from __future__ import annotations

import re

import pytest

from tests.acceptance.helpers import DOBRCZ, html

ADVISOR_ONLY = ("CSI", "POD", "FAR", "Peirce", "Brier", "BSS")
FARMER_WORDS = ("trafność", "trafność zrównoważona", "czułość", "precyzja", "zawsze częstsza odpowiedź")


def _farmer_text(page: str) -> str:
    page = re.sub(r'<div class="advisor".*?</div>', " ", page, flags=re.S)
    page = re.sub(r'<details class="calc".*?</details>', " ", page, flags=re.S)
    page = re.sub(r"<(script|style|title|desc)\b.*?</\1>", " ", page, flags=re.S)
    return re.sub(r"<[^>]+>", " ", page)


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_scores_give_the_farmer_measures_and_the_majority_answer() -> None:
    from app.models import ConfusionTable
    from app.validation.agreement import scores

    s = scores(ConfusionTable(hits=10, false_alarms=5, misses=10, correct_negatives=75))
    assert s["accuracy"] == pytest.approx(0.85)
    assert s["recall"] == pytest.approx(0.5)
    assert s["precision"] == pytest.approx(10 / 15)
    assert s["balanced_accuracy"] == pytest.approx((0.5 + 75 / 80) / 2)
    assert s["accuracy_majority"] == pytest.approx(0.8)  # "always no drought": 80 of 100 cases
    for key in ("csi", "pod", "far", "peirce"):
        assert s[key] is not None


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_farmer_view_shows_accuracy_next_to_the_trivial_answer() -> None:
    text = _farmer_text(html(DOBRCZ)).lower()
    for word in FARMER_WORDS:
        assert word in text, word


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_farmer_view_has_no_verification_scores() -> None:
    text = _farmer_text(html(DOBRCZ))
    for word in ADVISOR_ONLY:
        assert not re.search(rf"\b{word}\b", text), word


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_advisor_view_names_and_explains_csi_pod_far_peirce() -> None:
    page = html(DOBRCZ, widok="doradca")
    advisor = " ".join(re.findall(r'<div class="advisor".*?</div>', page, flags=re.S))
    for word in ("CSI", "POD", "FAR", "Peirce"):
        sentence = re.search(rf"\b{word}\b[^.]*\.", advisor)
        assert sentence and len(sentence.group(0)) > len(word) + 15, word
