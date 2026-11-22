"""K5: any parcel in Poland is fetched even when ULDK answers with a decoy.

In the demo room ULDK may redirect to a fake endpoint (`integracja01.gugik.gov.pl/resp/uldk.php`) that sends
`Content-Length: 4 GiB`, `text/html`, `Content-Disposition: attachment` and an endless hex stream. The parcel
lookup must refuse it without reading more than 2 MB, fall back to the EGiB WFS (layer `ms:dzialki`) and answer
in under 9 s. The tests use a mocked network (httpx.MockTransport through `http.set_client`), so they say nothing
about how the real services behave from the room's network.
"""

from __future__ import annotations

import json
import re
import time
from urllib.parse import unquote

import httpx
import pytest
from pyproj import Transformer

from app.geodata import fetch_parcel, http
from app.geodata.errors import UpstreamError
from app.geodata.parcel import fetch_parcel_by_lonlat
from tests.conftest import fixture_text

ULDK_HOST = "uldk.gugik.gov.pl"
DECOY_HOST = "integracja01.gugik.gov.pl"
WFS_HOST = "mapy.geoportal.gov.pl"
PARCEL_ID = "040303_2.0002.189/13"
OTHER_ID = "040303_2.0002.190/1"
MAX_READ = 2 * 1024 * 1024
CHUNK = 64 * 1024
HUGE = 16 * 1024 * 1024


def _square(x: float, y: float, side: float = 40.0) -> list[list[float]]:
    return [[x, y], [x + side, y], [x + side, y + side], [x, y + side], [x, y]]


def _feature(parcel_id: str, ring: list[list[float]]) -> dict:
    return {
        "type": "Feature",
        "properties": {
            "ID_DZIALKI": parcel_id,
            "NUMER_DZIALKI": parcel_id.rsplit(".", 1)[-1],
            "NAZWA_OBREBU": "Dobrcz",
            "NAZWA_GMINY": "Dobrcz",
        },
        "geometry": {"type": "Polygon", "coordinates": [ring]},
    }


class Network:
    """ULDK behaviour is set per test; the WFS answers with GeoJSON in EPSG:2180 (x = easting, y = northing)."""

    def __init__(self, uldk: str, *, wfs_ok: bool = True, features: list[dict] | None = None) -> None:
        self.uldk, self.wfs_ok, self.features = uldk, wfs_ok, features
        self.hosts: list[str] = []
        self.streamed = 0
        self.wfs_urls: list[str] = []

    def endless(self) -> object:
        def chunks():
            yield b"0\n"
            while (
                self.streamed < HUGE
            ):  # stands for an endless stream, but ends so a bad client cannot hang the suite
                self.streamed += CHUNK
                yield b"01" * (CHUNK // 2)

        return chunks()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        self.hosts.append(host)
        if host == DECOY_HOST:
            return httpx.Response(200, headers={"content-type": "text/html"}, content=self.endless())
        if host == ULDK_HOST:
            if self.uldk == "redirect":
                return httpx.Response(302, headers={"location": f"https://{DECOY_HOST}/resp/uldk.php"})
            if self.uldk == "endless_plain":
                return httpx.Response(200, headers={"content-type": "text/plain"}, content=self.endless())
            if self.uldk == "html":
                body = fixture_text("uldk_ok.txt")
                return httpx.Response(200, headers={"content-type": "text/html"}, content=body.encode())
            if self.uldk == "no_srid":
                body = "0\n" + "01" * 200
                return httpx.Response(200, headers={"content-type": "text/plain"}, content=body.encode())
            if self.uldk == "ok":
                body = fixture_text("uldk_ok.txt")
                return httpx.Response(
                    200, headers={"content-type": "text/plain; charset=UTF-8"}, content=body.encode()
                )
            raise httpx.ConnectTimeout("no answer")
        if host == WFS_HOST:
            self.wfs_urls.append(unquote(str(request.url)))
            if not self.wfs_ok:
                return httpx.Response(500, text="error")
            features = self.features
            if features is None:
                found = re.search(r"\d{6}_\d\.\d{4}\.[^<&\"]+", unquote(str(request.url)))
                features = [_feature(found.group(0) if found else PARCEL_ID, _square(442116.79, 601130.26))]
            body = {"type": "FeatureCollection", "features": features}
            return httpx.Response(
                200, headers={"content-type": "application/json"}, content=json.dumps(body).encode()
            )
        raise AssertionError(f"unexpected host {host}")


def install(net: Network) -> Network:
    http.set_client(httpx.Client(transport=httpx.MockTransport(net)))
    return net


@pytest.mark.xfail(reason="not built yet", strict=False)
@pytest.mark.parametrize("uldk", ["redirect", "endless_plain", "html", "no_srid", "silent"])
def test_decoy_or_silent_uldk_falls_back_to_the_wfs_in_under_9_s(uldk):
    net = install(Network(uldk))
    started = time.monotonic()
    result = fetch_parcel(PARCEL_ID)
    assert time.monotonic() - started < 9
    assert result.data.id == PARCEL_ID
    assert result.data.rings_2180[0][0] == [442116.79, 601130.26]
    assert WFS_HOST in net.hosts
    assert DECOY_HOST not in net.hosts, "a redirect to another host must not be followed"
    assert net.streamed <= MAX_READ + CHUNK, "no query may read more than 2 MB"


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_decoy_trips_a_five_minute_breaker():
    net = install(Network("redirect"))
    fetch_parcel(PARCEL_ID)
    before = net.hosts.count(ULDK_HOST)
    assert before >= 1
    result = fetch_parcel(OTHER_ID)
    assert result.data.id == OTHER_ID
    assert net.hosts.count(ULDK_HOST) == before, "after the first decoy ULDK is skipped"


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_a_proper_uldk_answer_does_not_touch_the_wfs():
    net = install(Network("ok"))
    result = fetch_parcel("100403_2.0011.144")
    assert result.data.id == "100403_2.0011.144"
    assert WFS_HOST not in net.hosts


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_both_sources_down_is_an_honest_error_within_the_budget():
    install(Network("silent", wfs_ok=False))
    started = time.monotonic()
    with pytest.raises(UpstreamError):
        fetch_parcel(PARCEL_ID)
    assert time.monotonic() - started < 9


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_click_fallback_picks_the_parcel_containing_the_point_and_keeps_axis_order():
    lon, lat = 18.1353, 53.2705
    x, y = Transformer.from_crs(4326, 2180, always_xy=True).transform(lon, lat)
    inside = _feature(PARCEL_ID, _square(x - 20, y - 20))
    neighbour = _feature(OTHER_ID, _square(x + 1.0, y - 20))  # touches a 2 m box around the point
    net = install(Network("redirect", features=[neighbour, inside]))
    result = fetch_parcel_by_lonlat(lon, lat)
    assert result.data.id == PARCEL_ID, "the point must lie inside the chosen outline"
    for url in net.wfs_urls:
        box = re.search(r"BBOX=([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+)", url)
        if box:  # urn:ogc:def:crs:EPSG::2180 is northing first
            assert abs(float(box.group(1)) - (y - 1)) < 5 and abs(float(box.group(2)) - (x - 1)) < 5
