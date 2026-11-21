"""Shared fixtures: every test gets an empty cache directory and a fake network built from recorded answers."""

from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from app.geodata import config, http, imgw, satellite, weather

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def map_png(width: int, height: int, layers: str) -> bytes:
    """Transparent map image; the ditch layer has one vertical line 100 px from the left edge."""
    import warnings

    import numpy as np
    import rasterio

    data = np.zeros((4, height, width), dtype="uint8")
    if layers == "row":
        data[0, :, 100:102], data[1, :, 100:102], data[2, :, 100:102] = 89, 217, 255
        data[3, :, 100:102] = 255
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with rasterio.MemoryFile() as memory:
            with memory.open(driver="PNG", width=width, height=height, count=4, dtype="uint8") as ds:
                ds.write(data)
            return memory.read()


class FakeNetwork:
    """Routes requests by host to recorded answers; counts calls; single hosts can be broken or slowed."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail: dict[str, int] = {}  # host fragment -> HTTP status to answer with
        self.delay: dict[str, float] = {}  # host fragment -> seconds to sleep before answering
        self.down = False

    def count(self, fragment: str) -> int:
        return sum(1 for url in self.calls if fragment in url)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.calls.append(url)
        if self.down:
            raise httpx.ConnectError("network is down", request=request)
        for fragment, seconds in self.delay.items():
            if fragment in url:
                time.sleep(seconds)
        for fragment, status in self.fail.items():
            if fragment in url:
                return httpx.Response(
                    status, json={"error": True, "reason": "Daily API request limit exceeded."}
                )
        host = request.url.host
        if host == "services.gugik.gov.pl":
            # Heights of a plane rising 1 m per 100 m to the east, rounded like the real service.
            pairs = [p.split() for p in parse_qs(request.content.decode())["list"][0].split(",")]
            return httpx.Response(
                200, text=",".join(f"{n} {e} {100 + (float(e) - 523000) / 100:.1f}" for n, e in pairs)
            )
        if "kompozycja_BDOT10k" in url:
            params = request.url.params
            return httpx.Response(
                200, content=map_png(int(params["WIDTH"]), int(params["HEIGHT"]), params["LAYERS"])
            )
        if host == "seasonal-api.open-meteo.com":
            return httpx.Response(200, text=fixture_text("open_meteo_seasonal.json"))
        if host == "uldk.gugik.gov.pl":
            found = "99999" not in url
            return httpx.Response(200, text=fixture_text("uldk_ok.txt" if found else "uldk_not_found.txt"))
        if host == "archive-api.open-meteo.com":
            return httpx.Response(200, text=fixture_text("open_meteo_archive.json"))
        if host == "api.open-meteo.com" and "/elevation" in url:
            n = len(request.url.params["latitude"].split(","))
            return httpx.Response(200, json={"elevation": [100.0 + i % 3 for i in range(n)]})
        if host == "api.open-meteo.com":
            return httpx.Response(200, text=fixture_text("open_meteo_forecast.json"))
        if host == "power.larc.nasa.gov":
            return httpx.Response(200, text=fixture_text("nasa_power_june.json"))
        if host == "rest.isric.org":
            null = request.url.params["lat"].startswith("52.2")
            return httpx.Response(
                200, text=fixture_text("soilgrids_null.json" if null else "soilgrids_ok.json")
            )
        if host == "mapy.geoportal.gov.pl" and "ORTO" in url:
            return httpx.Response(200, content=(FIXTURES / "ortho_48px.jpg").read_bytes())
        if host == "mapy.geoportal.gov.pl":
            return httpx.Response(503, text="terrain service unavailable")
        if "stac" in url or "earth-search" in host:
            return httpx.Response(200, text=json.dumps(self.stac_payload))
        return httpx.Response(404, text="unknown host in test")

    stac_payload: dict = {"features": []}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("GEODATA_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("GEODATA_OFFLINE", raising=False)
    monkeypatch.setenv("GEODATA_STAC", "earth-search")
    config.set_offline(None)
    monkeypatch.setattr(weather, "_archive_blocked_until", 0.0)
    monkeypatch.setattr(config, "EUCROPMAP_URL", str(tmp_path / "no_crop_map.tif"))
    imgw._loaded.clear()
    satellite._token.update(value="", expires=0.0)
    yield
    config.set_offline(None)
    http.set_client(None)


@pytest.fixture
def net():
    network = FakeNetwork()
    http.set_client(httpx.Client(transport=httpx.MockTransport(network)))
    return network
