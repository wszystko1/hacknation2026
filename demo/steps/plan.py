"""Scene "Plan działań: przełącznik „W planie”": switching an action on raises the plan counter from N to N+1."""

from demo.steps.common import PAUSE, open_row
from demo.steps.tabs import show_tab


def scene(page, base_url: str) -> None:
    show_tab(page, "rekomendacje")
    open_row(page, "plan")
    counter = page.locator("#licznik-planu [data-plan-count]")
    before = int(counter.inner_text())
    switch = page.locator("#wiersz-plan .sw").first
    switch.scroll_into_view_if_needed()
    page.wait_for_timeout(PAUSE)
    switch.click()
    page.wait_for_timeout(500)
    after = int(counter.inner_text())
    assert after == before + 1, (before, after)
    assert page.locator("#wiersz-plan li.is-planned").count() == after
    page.locator("#licznik-planu").scroll_into_view_if_needed()
    page.wait_for_timeout(PAUSE)
    show_tab(page, "podsumowanie")
