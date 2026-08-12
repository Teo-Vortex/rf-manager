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


def test_create_and_list_remote_device() -> None:
    with TestClient(app) as client:
        created = client.post("/api/devices", json={
            "name": "Test Remote", "device_type": "remote_control", "area": "Lab",
            "codes": [{"code": "ABC123", "action": "Open", "protocol": 1, "bits": 24, "pulse": 350}],
        })
        assert created.status_code == 201
        device = created.json()
        assert device["name"] == "Test Remote"
        assert device["codes"][0]["code"] == "ABC123"
        assert any(item["id"] == device["id"] for item in client.get("/api/devices").json())
        assert client.delete(f"/api/devices/{device['id']}").status_code == 204
