"""Scene "Zgodność z oceną państwa (SMSR)": accuracy beside the answer "always the more frequent one", then the
calibration curve of the advisor view with the parcel's mark and the frame sentence read from the curve."""

import json
from pathlib import Path

from demo.steps.common import PAUSE, open_row
from demo.steps.tabs import show_tab

SMSR = json.loads((Path(__file__).resolve().parents[2] / "metrics.json").read_text(encoding="utf-8"))["smsr"]


def _pct(x: float) -> str:
    return f"{100 * x:.1f}".replace(".", ",") + "%"


def scene(page, base_url: str) -> None:
    show_tab(page, "wiarygodnosc")
    open_row(page, "gmina")
    row = page.locator("#wiersz-gmina")
    text = row.inner_text()
    assert _pct(SMSR["accuracy"]) in text
    assert _pct(SMSR["accuracy_majority"]) in text
    assert "zawsze częstsza odpowiedź" in text
    assert "–" not in text.replace("−", "")
    page.wait_for_timeout(PAUSE)

    show_tab(page, "podsumowanie")
    page.locator("#pokaz-doradcy").click()
    page.wait_for_selector("#krzywa-kalibracji", timeout=30000)
    marker = page.locator("#krzywa-kalibracji [data-marker]")
    key = marker.get_attribute("data-marker")
    share = SMSR["calibration"]["fao56"][key]["plus_share"]
    frame = page.locator("#zgodnosc-ramka").inner_text()
    assert f"w {round(100 * share)} na 100 przypadków" in frame
    assert len(page.locator("#po-latach tbody tr").all()) == 7
    page.locator("#krzywa-kalibracji").scroll_into_view_if_needed()
    page.wait_for_timeout(PAUSE)
    # the next scene starts on the farmer screen (it clicks "Pokaż doradcy" itself): leave the advisor view
    page.go_back()
    page.wait_for_selector("#pokaz-doradcy")
