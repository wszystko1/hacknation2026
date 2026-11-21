"""Scene "Źródła, czasy i braki danych": the sources table with what each source gave, time and state."""

from demo.steps.common import PAUSE, open_section


def scene(page, base_url: str) -> None:
    page.locator("#skrot").scroll_into_view_if_needed()
    open_section(page, "Źródła i braki", "zrodla")
    table = page.locator("#tabela-zrodel")
    rows = table.locator("tbody tr")
    assert rows.count() >= 8, rows.count()
    text = table.inner_text()
    assert "Obrys działki" in text and "Prognoza 16 dni" in text
    assert "sezonow" not in text.lower()
    sentinel = table.locator("tr", has_text="Zdjęcie satelitarne").inner_text()
    assert "zdjęcie z" in sentinel or "ocena roślin w toku" in sentinel, sentinel
    assert "drenowania, wód gruntowych ani faktycznej daty siewu" in page.locator("#zrodla").inner_text()
    table.scroll_into_view_if_needed()
    page.wait_for_timeout(PAUSE)
