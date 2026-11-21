"""Index computation on small synthetic rasters (written by the test, values chosen by hand)."""

from datetime import date

import numpy as np
import pytest
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin

from app.geodata import fetch_satellite
from app.geodata.parcel import parse_uldk

from .conftest import fixture_text

EPSG = 32634


def write_band(path, value, pixel, x0, y_top, size_m=800):
    n = int(size_m / pixel)
    data = np.full((n, n), value, dtype="uint16")
    with rasterio.open(
        path, "w", driver="GTiff", width=n, height=n, count=1, dtype="uint16", crs=f"EPSG:{EPSG}",
        transform=from_origin(x0, y_top, pixel, pixel), nodata=0,
    ) as ds:  # fmt: skip
        ds.write(data, 1)
    return str(path)


def make_scene(tmp_path, parcel, name, day, *, red, nir, nir08, swir, scl, cloud=5.0):
    x, y = Transformer.from_crs(2180, EPSG, always_xy=True).transform(*parcel.centroid_2180)
    x0, y_top = round(x / 20) * 20 - 400, round(y / 20) * 20 + 400
    folder = tmp_path / name
    folder.mkdir()
    values = {"B04": (red, 10), "B08": (nir, 10), "B8A": (nir08, 20), "B11": (swir, 20), "SCL": (scl, 20)}
    assets = {k: {"href": write_band(folder / f"{k}.tif", v, px, x0, y_top)} for k, (v, px) in values.items()}
    props = {
        "datetime": f"{day}T10:00:00Z",
        "eo:cloud_cover": cloud,
        "proj:epsg": EPSG,
        "s2:processing_baseline": "05.11",
    }
    return {"id": name, "properties": props, "assets": assets}


@pytest.fixture
def parcel():
    return parse_uldk(fixture_text("uldk_ok.txt"))


def test_indices_use_the_offset_and_the_cloud_mask(net, tmp_path, parcel):
    # Digital numbers carry the +1000 offset of processing baseline 05.11: reflectance = (DN - 1000) / 10000.
    clear = make_scene(
        tmp_path, parcel, "clear", "2024-06-18", red=1500, nir=5000, nir08=5000, swir=3000, scl=4
    )
    cloudy = make_scene(
        tmp_path, parcel, "cloudy", "2024-06-20", red=9000, nir=9000, nir08=9000, swir=9000, scl=9
    )
    net.stac_payload = {"features": [cloudy, clear]}
    result = fetch_satellite(parcel, date(2024, 6, 20), history_years=0, today=date(2026, 11, 21))
    scene = result.data.current
    assert result.status == "ok" and scene.scene_id == "clear" and scene.days_from_target == -2
    assert scene.ndvi == pytest.approx((0.4 - 0.05) / (0.4 + 0.05), abs=1e-3)
    assert scene.ndmi == pytest.approx((0.4 - 0.2) / (0.4 + 0.2), abs=1e-3)
    assert scene.valid_fraction == 1.0 and scene.pixels > 100
    net.down = True
    assert fetch_satellite(parcel, date(2024, 6, 20), history_years=0, today=date(2026, 11, 21)).from_cache


def test_fully_clouded_parcel_gives_no_index(net, tmp_path, parcel):
    cloudy = make_scene(
        tmp_path, parcel, "cloudy", "2024-06-20", red=9000, nir=9000, nir08=9000, swir=9000, scl=9
    )
    net.stac_payload = {"features": [cloudy]}
    result = fetch_satellite(parcel, date(2024, 6, 20), history_years=0, today=date(2026, 11, 21))
    assert result.status == "fallback" and result.data.current is None
    assert any("cloud-free" in note for note in result.notes)


def test_dates_before_the_archive_are_skipped_without_network(net, parcel):
    result = fetch_satellite(parcel, date(2016, 5, 1))
    assert result.status == "skipped" and net.calls == []
