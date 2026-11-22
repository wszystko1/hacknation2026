"""The app is called ChrońPlon: the old name is gone from the visible text of every screen, the titles carry the new one."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.acceptance.helpers import DOBRCZ, html

client = TestClient(app)
OLD = re.compile(r"Bilans dzia[łl]ki")


def visible(page: str) -> str:
    page = re.sub(r"<(script|style)\b.*?</\1>", " ", page, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page))


def test_start_report_and_404_use_the_new_name() -> None:
    pages = {
        "start": client.get("/").text,
        "report": html(DOBRCZ),
        "404": client.get("/nie-ma-takiej-strony", headers={"accept": "text/html"}).text,
    }
    for name, page in pages.items():
        assert "ChrońPlon" in re.search(r"<title>(.*?)</title>", page, flags=re.S).group(1), name
        assert not OLD.search(visible(page)), name


def test_404_page_is_the_apps_own_with_a_link_home() -> None:
    r = client.get("/nie-ma-takiej-strony", headers={"accept": "text/html"})
    assert r.status_code == 404 and 'href="/"' in r.text and "Nowa ocena" in r.text
    assert client.get("/api/nie-ma", headers={"accept": "text/html"}).json() == {"detail": "Not Found"}


@pytest.mark.parametrize("path", ["/raport/sekcja/nie-ma"])
def test_other_errors_keep_their_status(path: str) -> None:
    assert client.get(path).status_code in (404, 422)
