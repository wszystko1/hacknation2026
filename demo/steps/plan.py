"""Scene "Plan działań: przełącznik „W planie”": switching an action on raises the plan counter from N to N+1."""

from demo.steps.common import PAUSE, open_section


def scene(page, base_url: str) -> None:
    counter = page.locator("[data-plan-count]").first
    before = int(counter.inner_text())
    switch = page.locator("#retencja .recs li .sw").first
    switch.scroll_into_view_if_needed()
    page.wait_for_timeout(500)
    switch.click()
    page.wait_for_timeout(500)
    open_section(page, "Plan i termin", "plan")
    after = int(counter.inner_text())
    assert after == before + 1, (before, after)
    page.wait_for_timeout(PAUSE)
