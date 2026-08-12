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


def test_duplicate_code_requires_explicit_override() -> None:
    payload = {"name": "First", "codes": [{"code": "DUP123", "action": "Open"}]}
    with TestClient(app) as client:
        first = client.post("/api/devices", json=payload).json()
        conflict = client.post("/api/devices", json={"name": "Second", "codes": [{"code": "dup123", "action": "Close"}]})
        assert conflict.status_code == 409
        assert conflict.json()["detail"]["conflicts"][0]["device_name"] == "First"
        allowed = client.post("/api/devices", json={"name": "Second", "allow_duplicates": True, "codes": [{"code": "DUP123", "action": "Close"}]})
        assert allowed.status_code == 201
        client.delete(f"/api/devices/{first['id']}")
        client.delete(f"/api/devices/{allowed.json()['id']}")


def test_update_device_and_replace_learned_code() -> None:
    with TestClient(app) as client:
        device = client.post("/api/devices", json={"name": "Old", "codes": [{"code": "OLD001", "action": "Button"}]}).json()
        updated = client.put(f"/api/devices/{device['id']}", json={"name": "New", "area": "Garage", "codes": [{"code": "NEW001", "action": "Gate"}]})
        assert updated.status_code == 200
        assert updated.json()["name"] == "New"
        assert updated.json()["codes"][0]["code"] == "NEW001"
        client.delete(f"/api/devices/{device['id']}")
