"""Open a tab of the farmer report (Podsumowanie, Przyczyny, Rekomendacje, Wiarygodność, Źródła) by its short name."""


def show_tab(page, name: str) -> None:
    page.locator(f'[data-tab-button="{name}"]:visible').first.click()
    page.wait_for_selector(f'[data-tab-button="{name}"][aria-selected="true"]')
