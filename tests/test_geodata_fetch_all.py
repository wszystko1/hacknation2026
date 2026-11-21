import json
import os

import pytest

from app.geodata import InvalidParcelId, config, fetch_all, list_samples, load_sample

PID = "100403_2.0011.144"


def test_all_sources_report_status_time_url_and_timestamp(net):
    result = fetch_all(PID, "2016-12-31", budget_s=20)
    assert result.core_ok
    assert set(result.sources()) == {
        "parcel", "weather", "ortho", "soil", "satellite", "terrain", "water", "forecast", "seasonal", "crop_hint",
    }  # fmt: skip
    for res in result.sources().values():
        assert res.status in {"ok", "fallback", "timeout", "error", "skipped"}
        assert res.source_url.startswith("https://") and res.retrieved_at
    assert result.parcel.status == "ok" and result.weather.status == "ok" and result.ortho.status == "ok"
    assert result.terrain.status == "ok" and result.water.status == "ok" and result.forecast.status == "ok"
    assert result.crop_hint.status == "error"  # the crop map is not reachable in tests
    payload = json.loads(json.dumps(result.to_dict()))
    assert payload["core_ok"] is True and payload["ortho"]["data"]["image"] is None
    assert payload["weather"]["data"]["dates"][-1] == "2016-12-31"


def test_second_call_is_served_from_disk_without_network(net):
    fetch_all(PID, "2016-12-31", budget_s=20)
    net.down = True
    again = fetch_all(PID, "2016-12-31", budget_s=20, offline=True)
    assert again.core_ok and again.total_ms < 1000
    assert all(r.from_cache for r in again.sources().values() if r.usable)
    assert config.is_offline() is False  # the per-call switch does not leak


def test_slow_optional_source_times_out_and_core_survives(net, monkeypatch):
    monkeypatch.setitem(config.TIMEOUTS, "soil", 0.3)
    net.delay["rest.isric.org"] = 1.5
    result = fetch_all(PID, "2016-12-31", budget_s=20, sources=("weather", "soil"))
    assert result.soil.status == "timeout" and result.core_ok
    assert result.ortho.status == "skipped" and result.total_ms < 1400


def test_total_budget_is_enforced(net):
    net.delay["archive-api"] = 2.0
    result = fetch_all(PID, "2016-12-31", budget_s=0.6, sources=("weather",))
    assert result.weather.status == "timeout" and not result.core_ok
    assert result.total_ms < 1200


def test_unknown_parcel_skips_the_rest(net):
    result = fetch_all("100403_2.0011.99999", "2016-12-31")
    assert result.parcel.status == "error" and "ParcelNotFound" in result.parcel.error
    assert all(r.status == "skipped" for n, r in result.sources().items() if n != "parcel")
    assert not result.core_ok


def test_offline_misses_are_reported_per_source(net):
    result = fetch_all(PID, "2016-12-31", offline=True)
    assert result.parcel.status == "error" and "offline" in result.parcel.error
    assert net.calls == []


def test_malformed_identifier_raises_before_any_request(net):
    with pytest.raises(InvalidParcelId):
        fetch_all("not a parcel", "2016-12-31")
    assert net.calls == []


def test_committed_samples_load_without_cache_or_network(net):
    samples = list_samples()
    assert len(samples) >= 2
    for parcel_id, day in samples:
        sample = load_sample(parcel_id, day)
        assert sample.core_ok and sample.parcel.data.area_ha > 0
        assert len(sample.weather.data.dates) > 3650
        assert sample.ortho.data.image.startswith(b"\xff\xd8")
        assert "demo sample" in sample.weather.notes[-1]
        assert sample.weather.data.precipitation_provider and sample.weather.data.et0_provider
    with_grid = [load_sample(*key) for key in samples]
    assert any(s.terrain.usable and s.terrain.data.grid is not None and s.water.usable for s in with_grid)
    assert net.calls == []


@pytest.mark.skipif(os.environ.get("GEODATA_LIVE") != "1", reason="live test: set GEODATA_LIVE=1")
@pytest.mark.live
def test_live_fetch_of_a_real_parcel():
    from app.geodata import http

    http.set_client(None)
    result = fetch_all("040303_2.0002.189/13", "2025-07-15", budget_s=30)
    assert result.core_ok, result.to_dict()
