"""The ULDK guard refuses the decoy without reading more than 2 MB and keeps ULDK closed for five minutes."""

from __future__ import annotations

import httpx
import pytest

from app.geodata import http, uldk_guard
from app.geodata.errors import UpstreamError
from tests.conftest import fixture_text

PARAMS = {"request": "GetParcelById", "id": "100403_2.0011.144"}
CHUNK = 64 * 1024
LIMIT = 2 * 1024 * 1024


class Server:
    def __init__(self, kind: str) -> None:
        self.kind, self.calls, self.streamed = kind, 0, 0

    def endless(self):
        yield b"0\n"
        while self.streamed < 16 * 1024 * 1024:
            self.streamed += CHUNK
            yield b"ab" * (CHUNK // 2)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        ok = fixture_text("uldk_ok.txt").encode()
        plain = {"content-type": "text/plain; charset=UTF-8"}
        match self.kind:
            case "redirect":
                return httpx.Response(
                    302, headers={"location": "https://integracja01.gugik.gov.pl/resp/uldk.php"}
                )
            case "html":
                return httpx.Response(200, headers={"content-type": "text/html"}, content=ok)
            case "attachment":
                headers = plain | {"content-disposition": "attachment; filename=x"}
                return httpx.Response(200, headers=headers, content=ok)
            case "no_srid":
                body = b"0\n100403_2.0011.144|a|b|c|d|144|POLYGON((1 1,2 2,3 3,1 1))"
                return httpx.Response(200, headers=plain, content=body)
            case "endless":
                return httpx.Response(200, headers=plain, content=self.endless())
            case "huge_length":
                return httpx.Response(
                    200, headers=plain | {"content-length": str(4 * 1024**3)}, content=b"0\n"
                )
            case _:
                return httpx.Response(200, headers=plain, content=ok)


@pytest.fixture
def now():
    clock = {"t": 1000.0}
    uldk_guard.set_clock(lambda: clock["t"])
    yield clock
    uldk_guard.set_clock(None)


def serve(kind: str) -> Server:
    server = Server(kind)
    http.set_client(httpx.Client(transport=httpx.MockTransport(server)))
    return server


def test_a_proper_answer_passes() -> None:
    serve("ok")
    answer = uldk_guard.fetch(PARAMS, geometry=True)
    assert answer.text.startswith("0\n100403_2.0011.144|")


@pytest.mark.parametrize("kind", ["redirect", "html", "attachment", "no_srid", "endless", "huge_length"])
def test_decoys_are_refused(kind: str, now) -> None:
    server = serve(kind)
    with pytest.raises(uldk_guard.UldkDecoy):
        uldk_guard.fetch(PARAMS, geometry=True)
    assert server.streamed <= LIMIT + CHUNK
    assert uldk_guard.breaker_open()


def test_a_redirect_to_the_decoy_host_is_not_followed() -> None:
    hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        if request.url.host == "uldk.gugik.gov.pl":
            return httpx.Response(
                302, headers={"location": "https://integracja01.gugik.gov.pl/resp/uldk.php"}
            )
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"x")

    http.set_client(httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True))
    with pytest.raises(uldk_guard.UldkDecoy):
        uldk_guard.fetch(PARAMS, geometry=True)
    assert hosts == ["uldk.gugik.gov.pl"]


def test_another_host_in_the_configuration_is_refused(monkeypatch) -> None:
    server = serve("ok")
    monkeypatch.setattr("app.geodata.config.ULDK_URL", "https://integracja01.gugik.gov.pl/resp/uldk.php")
    with pytest.raises(UpstreamError):
        uldk_guard.fetch(PARAMS, geometry=True)
    assert server.calls == 0


def test_after_the_first_decoy_the_second_query_does_not_touch_uldk_for_five_minutes(now) -> None:
    server = serve("redirect")
    with pytest.raises(uldk_guard.UldkDecoy):
        uldk_guard.fetch(PARAMS, geometry=True)
    assert server.calls == 1
    now["t"] += 299
    with pytest.raises(uldk_guard.UldkSkipped):
        uldk_guard.fetch(PARAMS, geometry=True)
    assert server.calls == 1
    now["t"] += 2  # 301 s after the decoy
    with pytest.raises(uldk_guard.UldkDecoy):
        uldk_guard.fetch(PARAMS, geometry=True)
    assert server.calls == 2


def test_an_error_status_line_is_passed_to_the_parser() -> None:
    http.set_client(
        httpx.Client(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(
                    200, headers={"content-type": "text/plain"}, content=b"-1 brak wynikow"
                )
            )
        )
    )
    assert uldk_guard.fetch(PARAMS, geometry=True).text.startswith("-1")
    assert not uldk_guard.breaker_open()
