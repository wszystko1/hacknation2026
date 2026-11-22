"""K4: the start form is pre-filled, so one click on "Oceń działkę" gives a result.

The defaults are the demo parcel 189/13 in Dobrcz, the date 20.07.2023 and the crop "Zboża jare"; every field can
still be changed, and a parcel picked on the map replaces the number.
"""

from __future__ import annotations

import re

import pytest

from tests.acceptance.helpers import client


def _start() -> str:
    r = client.get("/")
    assert r.status_code == 200
    return r.text


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_start_form_has_a_default_parcel_date_and_crop() -> None:
    page = _start()
    assert re.search(r'id="f-dzialka"[^>]*value="040303_2\.0002\.189/13"', page)
    assert re.search(r'id="f-data"[^>]*value="20\.07\.2023"', page)
    assert re.search(r'<option value="zboza_jare"\s+selected', page)
