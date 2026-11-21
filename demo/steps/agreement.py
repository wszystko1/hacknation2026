"""Scene "Zgodność z oceną państwa (SMSR)": accuracy beside the answer "always the more frequent one"."""

import json
from pathlib import Path

from demo.steps.common import PAUSE, open_section

SMSR = json.loads((Path(__file__).resolve().parents[2] / "metrics.json").read_text(encoding="utf-8"))["smsr"]


def _pct(x: float) -> str:
    return f"{100 * x:.1f}".replace(".", ",") + "%"


def scene(page, base_url: str) -> None:
    page.locator("#skrot").scroll_into_view_if_needed()
    open_section(page, "Gmina i trafność", "gmina")
    miary = page.locator("#miary")
    miary.scroll_into_view_if_needed()
    text = miary.inner_text()
    assert _pct(SMSR["accuracy"]) in text
    assert _pct(SMSR["accuracy_majority"]) in text
    assert "zawsze częstsza odpowiedź" in text
    assert "–" not in page.locator("#gmina").inner_text().replace("−", "")
    page.wait_for_timeout(PAUSE)
