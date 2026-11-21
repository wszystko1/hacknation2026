"""Scene "Działka z ewidencji na zdjęciu": number, date and crop typed in at 1366x768, one request, the photo first."""

from demo.steps.common import PARCEL_1, PAUSE

LAPTOP = {"width": 1366, "height": 768}
DATE_TYPED = "20.07.2023"


def _fits(page, selector: str) -> tuple[int, int]:
    """(scrollWidth, clientWidth) of an input: equal or smaller scrollWidth means the text is not cut off."""
    return page.eval_on_selector(selector, "el => [el.scrollWidth, el.clientWidth]")


def scene(page, base_url: str) -> None:
    previous = page.viewport_size
    page.set_viewport_size(LAPTOP)
    requests: list[str] = []

    def count(request) -> None:
        path = request.url.split("?")[0]
        if path.endswith("/raport"):
            requests.append(path)

    page.on("request", count)

    page.goto(base_url + "/")
    page.locator("#f-dzialka").click()
    page.locator("#f-dzialka").press_sequentially(PARCEL_1["dzialka"], delay=25)
    page.locator("#f-data").click()
    page.locator("#f-data").press_sequentially(
        DATE_TYPED.replace(".", ""), delay=40
    )  # the mask adds the dots
    page.locator("#f-uprawa").select_option(PARCEL_1["uprawa"])
    assert page.input_value("#f-dzialka") == PARCEL_1["dzialka"]
    assert page.input_value("#f-data") == DATE_TYPED, page.input_value("#f-data")
    scroll, client = _fits(page, "#f-dzialka")
    assert scroll <= client, f"the parcel number is cut off: {scroll} > {client}"
    assert "07/20/2023" not in page.content()
    page.wait_for_timeout(600)

    page.get_by_role("button", name="Oceń działkę").first.dblclick()
    page.wait_for_selector(".report-head", timeout=30000)
    page.remove_listener("request", count)
    assert len(requests) == 1, f"double click sent {len(requests)} requests to /raport"

    assert page.input_value("#f-dzialka") == PARCEL_1["dzialka"]
    assert page.input_value("#f-data") == DATE_TYPED
    scroll, client = _fits(page, "#f-dzialka")
    assert scroll <= client, f"the parcel number is cut off: {scroll} > {client}"
    assert "07/20/2023" not in page.content()
    assert "gm. Dobrcz › obręb Dobrcz" in page.locator(".crumb").inner_text()
    assert "21,53 ha" in page.locator(".sub").inner_text()
    page.locator(".map img").first.wait_for(state="visible")
    assert page.locator(".map svg .mo-outline").count() == 1
    page.wait_for_timeout(PAUSE)
    if previous:
        page.set_viewport_size(previous)
