"""Open a tab of the farmer report (Podsumowanie, Przyczyny, Rekomendacje, Wiarygodność, Źródła) by its short name."""


def show_tab(page, name: str) -> None:
    page.locator(f'[data-tab-button="{name}"]:visible').first.click()
    page.wait_for_selector(f'[data-tab-button="{name}"][aria-selected="true"]:visible')


def open_row(page, row_id: str) -> None:
    """Show a group of the farmer report: plain sections are always open; a folded block is opened."""
    row = page.locator(f"#wiersz-{row_id}")
    if row.evaluate("e => e.tagName") == "DETAILS" and row.get_attribute("open") is None:
        row.locator("summary").click()
    row.scroll_into_view_if_needed()
    page.wait_for_timeout(400)
