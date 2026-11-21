"""One test per route: each answers on the demo parcels without network (frozen copies in demo/data)."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
P1 = "dzialka=040303_2.0002.189/13&data=2023-07-20&uprawa=zboza_jare"


def test_health() -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_start_screen_has_the_three_fields_and_examples() -> None:
    html = client.get("/").text
    for text in (
        "Działka",
        "Data oceny",
        "Uprawa",
        "Oceń działkę",
        "kopia danych z 21.11.2026",
        "Zboża jare",
    ):
        assert text in html


def test_report_page_names_the_parcel() -> None:
    r = client.get(f"/raport?{P1}")
    assert r.status_code == 200
    assert "gm. Dobrcz › obręb Dobrcz" in r.text
    assert "21,53 ha" in r.text


def test_report_rejects_a_bad_number_next_to_the_field() -> None:
    r = client.get("/raport?dzialka=abc&data=2023-07-20&uprawa=zboza_jare")
    assert r.status_code == 422
    assert "Numer ma postać 040303_2.0002.189/13" in r.text


def test_print_view() -> None:
    r = client.get(f"/raport/druk?{P1}")
    assert r.status_code == 200
    assert "Widok do druku" in r.text


def test_section_fragment() -> None:
    r = client.get(f"/raport/sekcja/zrodla?{P1}")
    assert r.status_code == 200
    assert 'id="tabela-zrodel"' in r.text
    assert client.get(f"/raport/sekcja/nie-ma?{P1}").status_code == 404


def test_parcel_photo_is_a_jpeg() -> None:
    r = client.get("/raport/zdjecie?dzialka=040303_2.0002.189/13&data=2023-07-20")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"


def test_api_crops_lists_14_groups_and_other() -> None:
    crops = client.get("/api/uprawy").json()
    assert len(crops) == 15
    assert crops[-1]["nazwa"] == "Inna uprawa"


def test_api_report_follows_the_contract() -> None:
    from app.models import Report

    r = client.get(f"/api/raport?{P1}")
    assert r.status_code == 200
    report = Report.model_validate(r.json())
    assert report.parcel.commune == "Dobrcz"
    assert [s.n for s in report.sections] == list(range(1, 9))


def test_api_report_errors_are_per_field() -> None:
    r = client.get("/api/raport?dzialka=&data=1999-01-01&uprawa=")
    assert r.status_code == 422
    fields = {e["field"] for e in r.json()["bledy"]}
    assert fields == {"dzialka", "data", "uprawa"}
