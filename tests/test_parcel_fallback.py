"""Parcel outline when ULDK answers with a decoy or not at all: the EGiB WFS, the axis order, honest errors."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib.parse import unquote

import httpx
import pytest
from fastapi.testclient import TestClient
from pyproj import Transformer

from app.geodata import fetch_parcel, http
from app.geodata.errors import ParcelNotFound, UpstreamError
from app.geodata.parcel import fetch_parcel_by_lonlat
from app.main import app

PID = "040303_2.0002.190/1"
OTHER = "040303_2.0002.191/2"
X0, Y0 = 442116.79, 601130.26  # easting, northing


def square(x: float, y: float, side: float = 40.0) -> list[list[float]]:
    return [[x, y], [x + side, y], [x + side, y + side], [x, y + side], [x, y]]


def feature(pid: str, ring: list[list[float]]) -> dict:
    props = {
        "ID_DZIALKI": pid,
        "NUMER_DZIALKI": pid.rsplit(".", 1)[-1],
        "NAZWA_OBREBU": "Dobrcz",
        "NAZWA_GMINY": "Dobrcz",
    }
    return {"type": "Feature", "properties": props, "geometry": {"type": "Polygon", "coordinates": [ring]}}


class Net:
    def __init__(self, uldk: str = "redirect", wfs: list[dict] | int | None = None) -> None:
        self.uldk, self.wfs = uldk, wfs
        self.hosts: list[str] = []
        self.urls: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.hosts.append(request.url.host)
        if request.url.host == "uldk.gugik.gov.pl":
            if self.uldk == "redirect":
                return httpx.Response(
                    302, headers={"location": "https://integracja01.gugik.gov.pl/resp/uldk.php"}
                )
            raise httpx.ConnectTimeout("silent")
        if request.url.host == "mapy.geoportal.gov.pl":
            self.urls.append(unquote(str(request.url)))
            if isinstance(self.wfs, int):
                return httpx.Response(self.wfs, text="error")
            found = re.search(r"\d{6}_\d\.\d{4}\.[^<&\"]+", self.urls[-1])
            features = (
                self.wfs
                if self.wfs is not None
                else [feature(found.group(0) if found else PID, square(X0, Y0))]
            )
            return httpx.Response(200, json={"type": "FeatureCollection", "features": features})
        raise AssertionError(request.url.host)


def install(net: Net) -> Net:
    http.set_client(httpx.Client(transport=httpx.MockTransport(net)))
    return net


def test_decoy_gives_the_wfs_outline_and_the_next_query_is_faster() -> None:
    net = install(Net())
    started = time.monotonic()
    first = fetch_parcel(PID)
    assert time.monotonic() - started < 9
    assert first.data.outline_source == "EGiB WFS"
    assert first.data.area_ha == pytest.approx(0.16, abs=0.001)  # 40 m x 40 m, computed from the geometry
    started = time.monotonic()
    fetch_parcel(OTHER)
    assert time.monotonic() - started < 5.5
    assert net.hosts.count("uldk.gugik.gov.pl") == 1


def test_both_sources_down_is_a_polish_sentence() -> None:
    install(Net(uldk="silent", wfs=500))
    with pytest.raises(UpstreamError, match="Usługi GUGiK"):
        fetch_parcel(PID)


def test_an_empty_wfs_answer_is_not_found() -> None:
    install(Net(wfs=[]))
    with pytest.raises(ParcelNotFound):
        fetch_parcel(PID)


def test_the_report_route_and_the_picker_route_do_not_fail_with_500() -> None:
    install(Net(uldk="silent", wfs=500))
    client = TestClient(app, raise_server_exceptions=False)
    assert (
        client.get("/api/raport?dzialka=040303_2.0002.190/1&data=2023-07-20&uprawa=zboza_jare").status_code
        < 500
    )
    assert (
        client.get("/raport?dzialka=040303_2.0002.190/1&data=2023-07-20&uprawa=zboza_jare").status_code < 500
    )
    answer = client.get("/api/dzialka?lon=18.5&lat=53.1")
    assert answer.status_code == 422
    assert "ULDK" in answer.json()["bledy"][0]["message"]


def test_click_through_the_decoy_returns_the_wfs_outline_and_the_number_field_still_works() -> None:
    lon, lat = 19.0, 52.0
    x, y = Transformer.from_crs(4326, 2180, always_xy=True).transform(lon, lat)
    install(Net(wfs=[feature(PID, square(x - 20, y - 20))]))
    client = TestClient(app)
    answer = client.get(f"/api/dzialka?lon={lon}&lat={lat}")
    assert answer.status_code == 200 and answer.json()["dzialka"] == PID
    assert client.get("/api/dzialka?lon=abc&lat=1").status_code == 422


def test_name_search_uses_the_wfs_when_uldk_is_a_decoy() -> None:
    from app.inputs import resolve_parcel

    install(Net())
    assert resolve_parcel("Dobrcz 190/1") == PID


def test_axis_order_is_northing_first_in_bbox_and_easting_first_in_geojson() -> None:
    lon, lat = 18.1353, 53.2705
    x, y = Transformer.from_crs(4326, 2180, always_xy=True).transform(lon, lat)
    inside = feature(PID, square(x - 20, y - 20))
    neighbour = feature(OTHER, square(x + 1.0, y - 20))  # touches the 2 m box, does not contain the point
    net = install(Net(wfs=[neighbour, inside]))
    result = fetch_parcel_by_lonlat(lon, lat)
    assert result.data.id == PID
    box = re.search(r"BBOX=([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+),", net.urls[0])
    assert box and abs(float(box[1]) - (y - 1)) < 0.01 and abs(float(box[2]) - (x - 1)) < 0.01
    assert result.data.rings_2180[0][0] == [round(x - 20, 2), round(y - 20, 2)]  # x = easting stayed first


def test_a_point_outside_every_returned_outline_is_refused() -> None:
    lon, lat = 18.1353, 53.2705
    x, y = Transformer.from_crs(4326, 2180, always_xy=True).transform(lon, lat)
    install(Net(wfs=[feature(OTHER, square(x + 1.0, y - 20))]))
    with pytest.raises(ParcelNotFound):
        fetch_parcel_by_lonlat(lon, lat)


def test_freeze_script_writes_the_map_file_within_one_megabyte(tmp_path: Path) -> None:
    from scripts import freeze_parcels

    install(Net(uldk="redirect", wfs=[feature(PID, square(X0, Y0))]))
    out = tmp_path / "parcels.json"
    freeze_parcels.freeze([PID], out)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["parcels"][0]["dzialka"] == PID and data["parcels"][0]["pobrano"] is True
    assert out.stat().st_size < 1_000_000
    shipped = Path(__file__).resolve().parents[1] / "demo" / "data" / "map" / "parcels.json"
    assert shipped.stat().st_size < 1_000_000
