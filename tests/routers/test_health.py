"""Tests for /livez and /readyz health endpoints."""


def test_livez_returns_200_and_ok(client):
    """GET /livez returns 200 with status OK."""
    response = client.get("/livez")

    assert response.status_code == 200
    assert response.json() == {"status": "OK"}


def test_readyz_returns_200_and_ok(client):
    """GET /readyz returns 200 with status OK."""
    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "OK"}


def test_health_endpoints_do_not_require_auth():
    """Livez and readyz work without Authorization header."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app(testing=True)
    # Use client without auth headers
    client = TestClient(app)

    livez_response = client.get("/livez")
    readyz_response = client.get("/readyz")

    assert livez_response.status_code == 200
    assert readyz_response.status_code == 200
