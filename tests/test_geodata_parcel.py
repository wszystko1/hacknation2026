import pytest

from app.geodata import InvalidParcelId, ParcelNotFound, fetch_parcel, normalize_parcel_id
from app.geodata.errors import CacheMiss
from app.geodata.parcel import parse_uldk

from .conftest import fixture_text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (" 040303_2.0004.121/7 ", "040303_2.0004.121/7"),
        ("100403_2.0011.144", "100403_2.0011.144"),
        ("161002_5.0021.ar_7.337/39", "161002_5.0021.AR_7.337/39"),
        ("040303_2.0004.121\\7", "040303_2.0004.121/7"),
    ],
)
def test_identifier_is_normalised(text, expected):
    assert normalize_parcel_id(text) == expected


@pytest.mark.parametrize("text", ["", "121/7", "040303.0004.121", "04030_2.0004.121", "abc_2.0004.121"])
def test_malformed_identifier_is_rejected_with_a_hint(text):
    with pytest.raises(InvalidParcelId, match="TERYT_type.precinct.number"):
        normalize_parcel_id(text)


def test_uldk_answer_is_parsed():
    parcel = parse_uldk(fixture_text("uldk_ok.txt"))
    assert parcel.id == "100403_2.0011.144"
    assert parcel.voivodeship == "łódzkie"
    assert parcel.commune == "Góra Świętej Małgorzaty"
    assert parcel.area_ha == pytest.approx(2.4786, abs=0.001)
    lon, lat = parcel.centroid_4326
    assert 19.3 < lon < 19.4 and 52.0 < lat < 52.2
    xmin, ymin, xmax, ymax = parcel.bbox_2180
    assert xmin < parcel.centroid_2180[0] < xmax and ymin < parcel.centroid_2180[1] < ymax
    assert parcel.rings_2180[0][0] == parcel.rings_2180[0][-1]
    assert len(parcel.rings_4326[0]) == len(parcel.rings_2180[0])


def test_multipolygon_counts_every_part():
    text = "0\nX_1.0001.1|w|p|g|o|1|SRID=2180;MULTIPOLYGON(((0 0,10 0,10 10,0 10,0 0)),((20 0,120 0,120 100,20 100,20 0)))"
    parcel = parse_uldk(text)
    assert parcel.area_ha == pytest.approx(1.01)
    assert parcel.rings_2180[0][0] == [20.0, 0.0]  # the largest part is the outline


def test_unknown_parcel_raises_not_found(net):
    with pytest.raises(ParcelNotFound, match="brak wynik"):
        fetch_parcel("100403_2.0011.99999")


def test_second_lookup_needs_no_network(net):
    first = fetch_parcel("100403_2.0011.144")
    net.down = True
    second = fetch_parcel("100403_2.0011.144")
    assert not first.from_cache and second.from_cache
    assert second.data == first.data
    assert second.retrieved_at == first.retrieved_at
    assert net.count("uldk") == 1


def test_offline_miss_is_reported(net):
    from app.geodata import config

    config.set_offline(True)
    with pytest.raises(CacheMiss):
        fetch_parcel("100403_2.0011.144")
    assert net.calls == []
