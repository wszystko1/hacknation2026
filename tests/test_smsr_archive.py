"""The archive download (resumable) and the commune sample used to measure agreement with SMSR."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

import httpx

from scripts import fetch_communes, fetch_smsr

FIXTURE = Path(__file__).parent / "fixtures" / "smsr" / "2023_0403043.html"
SAMPLE = Path(__file__).resolve().parents[1] / "demo" / "data" / "eval" / "gminy.csv"


def client(calls: list[str], broken: set[str] = frozenset()) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if any(code in str(request.url) for code in broken):
            return httpx.Response(404, text="brak")
        return httpx.Response(200, text=FIXTURE.read_text(encoding="utf-8"))

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_archive_saves_pages_with_the_time_and_resumes(tmp_path: Path) -> None:
    calls: list[str] = []
    teryts = ["0403043", "0203022"]
    first = fetch_smsr.run(client(calls), teryts, range(2020, 2023), tmp_path, pause_s=0)
    assert first == {"downloaded": 6, "already_there": 0, "failed": 0}
    assert (tmp_path / "2021_0203022.html").exists()
    assert "elapsed_s" in (tmp_path / "2021_0203022.json").read_text(encoding="utf-8")

    (tmp_path / "2022_0203022.html").unlink()  # an interrupted run
    calls.clear()
    second = fetch_smsr.run(client(calls), teryts, range(2020, 2023), tmp_path, pause_s=0)
    assert second == {"downloaded": 1, "already_there": 5, "failed": 0}
    assert calls == ["https://susza.iung.pulawy.pl/wykazy/2022,0203022/"]


def test_archive_lists_what_it_could_not_get_and_leaves_no_half_page(tmp_path: Path) -> None:
    result = fetch_smsr.run(
        client([], broken={"0203022"}), ["0403043", "0203022"], range(2020, 2022), tmp_path, 0
    )
    assert result == {"downloaded": 2, "already_there": 0, "failed": 2}
    assert (tmp_path / "failed.txt").read_text(encoding="utf-8").split() == ["2020_0203022", "2021_0203022"]
    assert not list(tmp_path.glob("*.part"))
    assert not (tmp_path / "2020_0203022.html").exists()


def test_a_page_that_is_not_a_table_is_not_saved(tmp_path: Path) -> None:
    maintenance = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text="<html>przerwa</html>"))
    )
    result = fetch_smsr.run(maintenance, ["0403043"], range(2023, 2024), tmp_path, pause_s=0)
    assert result["failed"] == 1 and not (tmp_path / "2023_0403043.html").exists()


def test_years_argument() -> None:
    assert list(fetch_smsr.parse_years("2020-2022")) == [2020, 2021, 2022]
    assert list(fetch_smsr.parse_years("2024")) == [2024]


def test_strata_sizes_add_up() -> None:
    assert sum(fetch_communes.quotas(16, 12, 200)) == 200
    assert sum(fetch_communes.quotas(16, 3, 50)) == 50


# ---------------------------------------------------------------- the committed sample


def rows() -> list[dict[str, str]]:
    with SAMPLE.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_sample_has_about_200_communes_and_the_agreed_columns() -> None:
    data = rows()
    assert list(data[0]) == ["teryt", "nazwa", "wojewodztwo", "lon", "lat", "zbior"]
    assert 190 <= len(data) <= 210
    assert len({r["teryt"] for r in data}) == len(data)


def test_sample_has_at_least_8_communes_in_each_of_16_voivodeships() -> None:
    per = Counter(r["wojewodztwo"] for r in rows())
    assert len(per) == 16
    assert min(per.values()) >= 8


def test_sample_splits_50_development_and_the_rest_test_in_every_voivodeship() -> None:
    data = rows()
    assert Counter(r["zbior"] for r in data) == {"dev": 50, "test": len(data) - 50}
    for woj in {r["wojewodztwo"] for r in data}:
        sets = {r["zbior"] for r in data if r["wojewodztwo"] == woj}
        assert sets == {"dev", "test"}, woj


def test_sample_coordinates_lie_in_poland_and_teryt_matches_the_voivodeship() -> None:
    for r in rows():
        assert 14.0 <= float(r["lon"]) <= 24.2 and 49.0 <= float(r["lat"]) <= 54.9, r
        assert len(r["teryt"]) == 7 and r["teryt"][-1] in {"2", "3"}, r
    code = {}
    for r in rows():
        code.setdefault(r["wojewodztwo"], set()).add(r["teryt"][:2])
    assert all(len(v) == 1 for v in code.values()), code
