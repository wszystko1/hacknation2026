import numpy as np
import pytest

from app.geodata import (
    fetch_crop_hint,
    fetch_forecast,
    fetch_ortho,
    fetch_seasonal,
    fetch_soil,
    fetch_terrain,
    fetch_water,
)
from app.geodata.ortho import image_frame
from app.geodata.parcel import parse_uldk
from app.geodata.soil import usda_texture_class
from app.geodata.terrain import grid_stats

from .conftest import fixture_text


@pytest.fixture
def parcel():
    return parse_uldk(fixture_text("uldk_ok.txt"))


def test_soil_texture_is_a_depth_weighted_mean(net):
    result = fetch_soil(53.1, 18.0)
    soil = result.data
    assert result.status == "ok" and soil.available
    assert soil.sand_pct + soil.silt_pct + soil.clay_pct == pytest.approx(100, abs=1.5)
    assert soil.clay_pct == pytest.approx((9.4 * 5 + 8.2 * 10 + 11.0 * 15) / 30, abs=0.1)
    assert soil.texture_class == "sandy loam"


def test_soil_null_answer_is_a_labelled_fallback_not_an_error(net):
    result = fetch_soil(52.2, 21.0)
    assert result.status == "fallback" and result.data.available is False
    assert result.data.sand_pct is None and result.data.texture_class is None
    assert any("null" in note for note in result.notes)


def test_soil_outage_is_a_labelled_fallback(net):
    net.fail["rest.isric.org"] = 503
    result = fetch_soil(53.1, 18.0)
    assert result.status == "fallback" and "503" in result.notes[0]


def test_texture_classes():
    assert usda_texture_class(92, 5, 3) == "sand"
    assert usda_texture_class(40, 40, 20) == "loam"
    assert usda_texture_class(20, 20, 60) == "clay"


def test_orthophoto_outline_lies_inside_the_image(net, parcel):
    result = fetch_ortho(parcel, max_px=256)
    ortho = result.data
    assert ortho.image.startswith(b"\xff\xd8") and max(ortho.width, ortho.height) == 256
    for col, row in ortho.polygon_px[0]:
        assert 0 <= col <= ortho.width and 0 <= row <= ortho.height
    assert "BBOX=" in result.source_url and "EPSG%3A2180" in result.source_url
    net.down = True
    assert fetch_ortho(parcel, max_px=256).from_cache


def test_image_frame_respects_pixel_size():
    frame, width, height, pixel = image_frame([0, 0, 200, 100], margin=0.25, m_per_px=0.5, max_px=1024)
    assert pixel == 0.5 and (width, height) == (600, 300)
    assert frame == [-50.0, -25.0, 250.0, 125.0]


def test_terrain_grid_comes_from_the_national_height_service(net, parcel):
    result = fetch_terrain(parcel, spacing_m=10, margin_m=50)
    terrain, grid = result.data, result.data.grid
    assert result.status == "ok" and terrain.provider == "gugik-nmt-points" and grid.crs == "EPSG:2180"
    assert (len(grid.z), len(grid.z[0])) == (grid.rows, grid.cols) == (len(grid.inside), len(grid.inside[0]))
    xmin, ymin, xmax, ymax = parcel.bbox_2180
    assert grid.x0 <= xmin - 45 and grid.y_top >= ymax + 45 and grid.step_m == 10
    assert terrain.slope_mean_pct == pytest.approx(1.0, abs=0.15)  # the fake service returns a 1 % plane
    assert terrain.samples == sum(map(sum, grid.inside)) > 100
    assert grid.z[0][-1] > grid.z[0][0]
    net.down = True
    again = fetch_terrain(parcel, spacing_m=10, margin_m=50)
    assert again.from_cache and again.data.grid.z == grid.z


def test_terrain_grid_is_widened_for_a_point_limit(net, parcel):
    result = fetch_terrain(parcel, spacing_m=2, max_points=500)
    assert result.data.grid.rows * result.data.grid.cols <= 560 and result.data.grid.step_m > 2
    assert any("widened" in note for note in result.notes)


def test_terrain_falls_back_in_order_and_says_so(net, parcel):
    net.fail["services.gugik.gov.pl"] = 500
    result = fetch_terrain(parcel)
    assert result.status == "fallback" and result.data.provider == "open-meteo-elevation"
    assert "height service" in result.notes[0] and "WCS" in result.notes[1] and "90 m" in result.resolution
    assert result.data.min_m <= result.data.mean_m <= result.data.max_m
    assert result.data.grid is not None and result.data.lowest_outline_point_2180 is not None


def test_ditch_distance_is_measured_from_the_parcel_boundary(net, parcel):
    result = fetch_water(parcel, search_m=500, pixel_m=2)
    water = result.data
    # The fake map draws a ditch 200-204 m east of the image edge, i.e. 296-300 m west of the parcel.
    assert result.status == "ok" and water.nearest_any_kind == "ditch"
    assert water.nearest_ditch_m == pytest.approx(296, abs=3)
    assert water.nearest_stream_m is None and water.nearest_water_body_m is None
    feature = water.features[0]
    assert feature.kind == "ditch" and feature.rings_2180[0][0] == feature.rings_2180[0][-1]
    assert feature.rings_2180[0][0][0] == pytest.approx(parcel.bbox_2180[0] - 300, abs=4)
    assert "GetCapabilities" not in " ".join(net.calls)
    net.down = True
    assert fetch_water(parcel, search_m=500, pixel_m=2).from_cache


def test_forecast_and_seasonal_outlook(net):
    forecast = fetch_forecast(52.1, 19.35).data
    assert forecast.days == len(forecast.dates) == len(forecast.precipitation_mm) > 0
    seasonal = fetch_seasonal(52.1, 19.35).data
    assert seasonal.members == 4 and len(seasonal.dates) == 12
    for low, mean, high in zip(
        seasonal.precipitation_p10_mm,
        seasonal.precipitation_mean_mm,
        seasonal.precipitation_p90_mm,
        strict=True,
    ):
        assert low <= mean + 1e-6 and low <= high


def test_crop_hint_histogram(net, parcel, tmp_path):
    import rasterio
    from pyproj import Transformer
    from rasterio.transform import from_origin

    x, y = Transformer.from_crs(2180, 3035, always_xy=True).transform(*parcel.centroid_2180)
    data = np.full((80, 80), 216, dtype="int32")
    data[:, :40] = 211
    path = tmp_path / "cropmap.tif"
    with rasterio.open(
        path, "w", driver="GTiff", width=80, height=80, count=1, dtype="int32", crs="EPSG:3035",
        transform=from_origin(round(x) - 400, round(y) + 400, 10, 10), nodata=0,
    ) as ds:  # fmt: skip
        ds.write(data, 1)
    result = fetch_crop_hint(parcel, url=str(path))
    hint = result.data
    assert result.status == "ok" and hint.map_year == 2022 and hint.pixels > 100
    assert {c.name for c in hint.classes} == {"Common wheat", "Maize"}
    assert sum(c.share for c in hint.classes) == pytest.approx(1.0, abs=0.01)
    assert any("hint" in note for note in result.notes)


def test_slope_of_a_tilted_plane(parcel):
    xmin, ymin, xmax, ymax = parcel.bbox_2180
    step = 5.0
    cols, rows = int((xmax - xmin) / step) + 4, int((ymax - ymin) / step) + 4
    x0, y_top = xmin - 2 * step, ymax + 2 * step
    z = 100.0 + 0.1 * step * np.tile(np.arange(cols), (rows, 1))  # rises 10 cm per metre to the east
    terrain = grid_stats(z, x0, y_top, step, parcel, "test")
    assert terrain.slope_mean_pct == pytest.approx(10.0, abs=0.01)
    west_edge = min(p[0] for p in parcel.rings_2180[0])
    assert terrain.lowest_outline_point_2180[0] == pytest.approx(west_edge, abs=step)
    assert terrain.max_m - terrain.min_m == pytest.approx(0.1 * (xmax - xmin), abs=1.5)
