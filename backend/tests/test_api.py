from fastapi.testclient import TestClient

from backend.app.main import app


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_mqtt_password_is_not_exposed() -> None:
    with TestClient(app) as client:
        response = client.get("/api/settings/mqtt")
        assert response.status_code == 200
        assert "password" not in response.json()


def test_diagnostic_logs_are_available() -> None:
    with TestClient(app) as client:
        response = client.get("/api/diagnostics/logs")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
