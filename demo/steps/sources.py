"""Scene "Źródła, czasy i braki danych": the sources table with what each source gave, time and state."""

from demo.steps.common import PAUSE
from demo.steps.tabs import show_tab


def scene(page, base_url: str) -> None:
    show_tab(page, "zrodla")
    folded = page.locator("#wiersz-zrodla")
    if folded.get_attribute("open") is None:
        folded.locator("summary").click()
    table = page.locator("#tabela-zrodel")
    rows = table.locator("tbody tr")
    assert rows.count() >= 8, rows.count()
    text = table.inner_text()
    assert "Obrys działki" in text and "Prognoza 16 dni" in text
    assert "sezonow" not in text.lower()
    sentinel = table.locator("tr", has_text="Zdjęcie satelitarne").inner_text()
    assert "zdjęcie z" in sentinel or "ocena roślin w toku" in sentinel, sentinel
    assert "drenowania, wód gruntowych ani faktycznej daty siewu" in page.locator("#poziom-b").inner_text()
    table.scroll_into_view_if_needed()
    page.wait_for_timeout(PAUSE)
