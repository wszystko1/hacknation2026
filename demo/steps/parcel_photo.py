"""Scene "Działka z ewidencji na zdjęciu": "To ta działka" on the map card, date and crop typed in at 1366x768,
one request, the photo first, then a click on the field west of the parcel: its outline and a card with its number.

The scene starts where "Wskazanie działki na mapie" ends: the card of parcel 189/13 on the start map.
"""

from demo.steps import map_pick
from demo.steps.common import PARCEL_1, PAUSE

LAPTOP = {"width": 1366, "height": 768}
DATE_TYPED = "20.07.2023"
WEST = (18.1300, 53.2705)  # lon, lat: about 160 m west of 189/13, on the field next to it


def _fits(page, selector: str) -> tuple[int, int]:
    """(scrollWidth, clientWidth) of an input: equal or smaller scrollWidth means the text is not cut off."""
    return page.eval_on_selector(selector, "el => [el.scrollWidth, el.clientWidth]")


def screen_point(page, lon: float, lat: float) -> tuple[float, float]:
    """Page coordinates of a point of the earth on the report photo (shown with object-fit: cover).

    Same arithmetic as app/static/neighbour.js, run from the corners the page publishes in data-corners-4326.
    """
    return page.evaluate(
        """([lon, lat]) => {
          const m = document.querySelector('.map'), box = m.getBoundingClientRect();
          const w = +m.dataset.width, h = +m.dataset.height;
          const c = m.getAttribute('data-corners-4326').split(' ').map(p => p.split(',').map(Number));
          const e1 = [c[1][0] - c[0][0], c[1][1] - c[0][1]], e2 = [c[2][0] - c[0][0], c[2][1] - c[0][1]];
          const det = e1[0] * e2[1] - e1[1] * e2[0], dx = lon - c[0][0], dy = lat - c[0][1];
          const col = (dx * e2[1] - dy * e2[0]) / det * w, row = (e1[0] * dy - e1[1] * dx) / det * h;
          const s = Math.max(box.width / w, box.height / h);
          return [box.left + (box.width - w * s) / 2 + col * s, box.top + (box.height - h * s) / 2 + row * s];
        }""",
        [lon, lat],
    )


def scene(page, base_url: str) -> None:
    previous = page.viewport_size
    page.set_viewport_size(LAPTOP)
    requests: list[str] = []

    def count(request) -> None:
        path = request.url.split("?")[0]
        if path.endswith("/raport"):
            requests.append(path)

    page.on("request", count)

    confirm = page.get_by_role("button", name="To ta działka")
    if not confirm.is_visible():  # run on its own: point at the parcel on the map first
        page.goto(base_url + "/")
        map_pick.tiles_loaded(page)
        map_pick.zoom_to_parcel(page)
        map_pick.click_parcel(page)
        confirm.wait_for(state="visible", timeout=15000)
    page.wait_for_timeout(PAUSE // 2)
    confirm.click()
    assert page.input_value("#f-dzialka") == PARCEL_1["dzialka"], page.input_value("#f-dzialka")
    page.wait_for_timeout(PAUSE // 2)
    page.locator("#f-data").click(click_count=3)  # the field is pre-filled: select it, then type over it
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
    assert page.input_value("#f-uprawa") == PARCEL_1["uprawa"]
    scroll, client = _fits(page, "#f-dzialka")
    assert scroll <= client, f"the parcel number is cut off: {scroll} > {client}"
    assert "07/20/2023" not in page.content()
    assert "gm. Dobrcz › obręb Dobrcz" in page.locator(".crumb").inner_text()
    assert "21,53 ha" in page.locator(".sub").inner_text()
    page.locator(".map img").first.wait_for(state="visible")
    assert page.locator(".map svg .mo-outline").count() == 1
    page.wait_for_timeout(PAUSE)

    # a click on the field west of the parcel proposes its neighbour; a click on the parcel itself does nothing
    card = page.locator("[data-nb-card]")
    page.mouse.click(*screen_point(page, 18.1353, 53.2705))
    page.wait_for_timeout(400)
    assert not card.is_visible()
    # Only when the server can name the parcel there: from the frozen copy offline or from ULDK online. A refusal
    # (422) is shown to a user in the card, but it would count as a console error in the recording.
    answer = page.request.get(f"{base_url}/api/dzialka?lon={WEST[0]}&lat={WEST[1]}")
    if answer.ok:
        page.mouse.click(*screen_point(page, *WEST))
        page.wait_for_selector("[data-nb-card][data-state=found]", timeout=15000)
        title = card.locator(".nb-title").inner_text()
        assert title.startswith("Sąsiednia działka ") and "189/13" not in title, title
        href = card.get_by_role("link", name="Otwórz raport tej działki").get_attribute("href") or ""
        assert "data=2023-07-20" in href and "uprawa=zboza_jare" in href, href
        assert page.locator(".mo-neighbour").count() == 1
        card.scroll_into_view_if_needed()
    page.wait_for_timeout(PAUSE)
    if previous:
        page.set_viewport_size(previous)
