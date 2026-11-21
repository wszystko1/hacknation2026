"""Scene "Źródła, czasy i braki danych": the sources table with time, duration and state."""

from demo.steps.common import PAUSE, open_section


def scene(page, base_url: str) -> None:
    page.locator("#skrot").scroll_into_view_if_needed()
    open_section(page, "Źródła i braki", "zrodla")
    rows = page.locator("#tabela-zrodel tbody tr")
    assert rows.count() >= 8, rows.count()
    assert "Obrys działki" in page.locator("#tabela-zrodel").inner_text()
    page.wait_for_timeout(PAUSE)
