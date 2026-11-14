import pytest
from fastapi.testclient import TestClient

from app.api.v1.health import get_db_check
from app.main import create_app


@pytest.fixture
def make_client():
    def _make(db_ok: bool) -> TestClient:
        app = create_app()
        app.dependency_overrides[get_db_check] = lambda: lambda: db_ok
        return TestClient(app)

    return _make


def test_health_ok(make_client):
    r = make_client(True).get("/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "db": "ok"}


def test_health_db_down(make_client):
    r = make_client(False).get("/v1/health")
    assert r.status_code == 503
    assert r.json() == {"status": "degraded", "db": "unavailable"}
