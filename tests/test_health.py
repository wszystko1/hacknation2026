from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}


def test_index_renders() -> None:
    client = TestClient(app)
    assert client.get("/").status_code == 200
