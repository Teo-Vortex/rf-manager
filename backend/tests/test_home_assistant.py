import json

from backend.app.config import Settings
from backend.app.db import Device, RFCode, SessionLocal
from backend.app.home_assistant import (
    command_topic,
    discovery_payload,
    event_discovery_payload,
    event_discovery_topic,
    event_state_topic,
    resolve_command,
    trigger_discovery_payload,
    trigger_discovery_topic,
    trigger_topic,
)


def test_discovery_creates_home_assistant_button() -> None:
    settings = Settings()
    device = Device(id=12, name="Garage Remote", area="Garage")
    code = RFCode(id=34, device_id=12, code="ABC123", action="Open")
    payload = json.loads(discovery_payload(settings, device, code))
    assert payload["unique_id"] == "rfmanager_12_34"
    assert payload["name"] == "Send Open"
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


def test_device_trigger_discovery_uses_dedicated_press_topic() -> None:
    settings = Settings()
    device = Device(id=12, name="Garage Remote", area="Garage")
    code = RFCode(id=34, device_id=12, code="ABC123", action="Open")
    payload = json.loads(trigger_discovery_payload(settings, device, code))
    assert trigger_discovery_topic(settings, 12, 34) == "homeassistant/device_automation/rfmanager_12/button_34/config"
    assert payload["automation_type"] == "trigger"
    assert payload["type"] == "button_short_press"
    assert payload["subtype"] == "Open"
    assert payload["payload"] == "PRESS"
    assert payload["topic"] == trigger_topic(settings, 12, 34)


def test_event_discovery_shows_last_physical_press() -> None:
    settings = Settings()
    device = Device(id=12, name="Garage Remote", area="Garage")
    code = RFCode(id=34, device_id=12, code="ABC123", action="Open")
    payload = json.loads(event_discovery_payload(settings, device, code))
    assert event_discovery_topic(settings, 12, 34) == "homeassistant/event/rfmanager_12_34_received/config"
    assert payload["name"] == "Received Open"
    assert payload["unique_id"] == "rfmanager_12_34_received"
    assert payload["state_topic"] == event_state_topic(settings, 12, 34)
    assert payload["event_types"] == ["press"]
    assert payload["device_class"] == "button"
