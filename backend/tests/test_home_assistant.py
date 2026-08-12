import json

from backend.app.config import Settings
from backend.app.db import Device, RFCode, SessionLocal
from backend.app.home_assistant import command_topic, discovery_payload, resolve_command


def test_discovery_creates_home_assistant_button() -> None:
    settings = Settings()
    device = Device(id=12, name="Garage Remote", area="Garage")
    code = RFCode(id=34, device_id=12, code="ABC123", action="Open")
    payload = json.loads(discovery_payload(settings, device, code))
    assert payload["unique_id"] == "rfmanager_12_34"
    assert payload["command_topic"] == "rfmanager/command/device/12/code/34/set"
    assert payload["device"]["name"] == "Garage Remote"
    assert payload["suggested_area"] == "Garage"


def test_home_assistant_press_resolves_saved_code() -> None:
    settings = Settings()
    with SessionLocal() as db:
        device = Device(name="HA Test")
        device.codes.append(RFCode(code="ABC123", action="Open"))
        db.add(device)
        db.commit()
        db.refresh(device)
        device_id, code_id = device.id, device.codes[0].id

    resolved = resolve_command(command_topic(settings, device_id, code_id), b"PRESS", settings)
    assert resolved is not None
    assert resolved.code == "ABC123"

    with SessionLocal() as db:
        saved = db.get(Device, device_id)
        db.delete(saved)
        db.commit()


def test_home_assistant_ignores_unknown_payload() -> None:
    assert resolve_command("rfmanager/command/device/1/code/2/set", b"NO", Settings()) is None
