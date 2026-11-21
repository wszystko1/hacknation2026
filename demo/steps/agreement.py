"""Scene "Zgodność z oceną państwa (SMSR)": the 2x2 table with CSI, POD, FAR and the number of commune-years."""

from demo.steps.common import PAUSE, open_section


def scene(page, base_url: str) -> None:
    page.locator("#skrot").scroll_into_view_if_needed()
    open_section(page, "Gmina i trafność", "gmina")
    assert page.locator("#tabela-2x2").is_visible()
    assert "CSI" in page.locator("#gmina .nums").inner_text()
    page.wait_for_timeout(PAUSE)
