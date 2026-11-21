"""Helpers shared by the scenes: the two demo parcels and the evaluation form."""

from __future__ import annotations

PARCEL_1 = {"dzialka": "040303_2.0002.189/13", "data": "2023-07-20", "uprawa": "zboza_jare"}
PARCEL_2 = {"dzialka": "100403_2.0011.144", "data": "2026-11-21", "uprawa": "rosliny_straczkowe"}
PAUSE = 1500


def evaluate(page, base_url: str, parcel: dict) -> None:
    """Type the parcel, the date and the crop on the start screen and click "Oceń działkę"."""
    page.goto(base_url + "/")
    page.locator("#f-dzialka").click()
    page.locator("#f-dzialka").press_sequentially(parcel["dzialka"], delay=25)
    page.locator("#f-data").fill(parcel["data"])
    page.locator("#f-uprawa").select_option(parcel["uprawa"])
    page.wait_for_timeout(600)
    page.get_by_role("button", name="Oceń działkę").first.click()
    page.wait_for_selector(".report-head", timeout=30000)


def open_section(page, toc_title: str, section_id: str) -> None:
    """Click a row of "Cały raport w skrócie" and wait until its section is on screen."""
    page.locator("#skrot a", has_text=toc_title).first.click()
    page.locator(f"#{section_id}").scroll_into_view_if_needed()
    page.wait_for_timeout(400)
