from unittest.mock import Mock

import pytest

from backend.app.config import Settings
from backend.app.mqtt_service import MQTTService
from backend.app.models import RFFrame


class FakeReasonCode:
    def __init__(self, is_failure: bool, label: str) -> None:
        self.is_failure = is_failure
        self.label = label

    def __str__(self) -> str:
        return self.label


def make_service() -> MQTTService:
    return MQTTService(Settings(), Mock())


def test_connect_accepts_paho_v2_reason_code() -> None:
    service = make_service()
    client = Mock()
    client.subscribe.return_value = (0, 1)

    service._on_connect(client, None, None, FakeReasonCode(False, "Success"), None)

    assert service.connected is True
    assert service.last_error is None
    client.subscribe.assert_any_call(service.settings.tasmota_receive_topic)
    client.subscribe.assert_any_call(f"{service.settings.ha_base_topic}/command/#")


def test_connect_reports_rejected_paho_v2_reason_code() -> None:
    service = make_service()
    client = Mock()

    service._on_connect(client, None, None, FakeReasonCode(True, "Not authorized"), None)

    assert service.connected is False
    assert service.last_error == "Connection rejected: Not authorized"


def test_subscription_rejection_is_reported() -> None:
    service = make_service()
    service._on_subscribe(Mock(), None, 7, [FakeReasonCode(True, "Not authorized")], None)
    assert service.last_error == "MQTT subscription rejected: Not authorized"


def test_subscription_confirmation_keeps_connection_clean() -> None:
    service = make_service()
    service._on_subscribe(Mock(), None, 7, [FakeReasonCode(False, "Granted QoS 0")], None)
    assert service.last_error is None


def test_publish_command_requires_connection() -> None:
    service = make_service()
    with pytest.raises(ConnectionError):
        service.publish_command("cmnd/bridge/RfCode", "#ABC123")


def test_known_rf_frame_publishes_home_assistant_device_trigger(monkeypatch) -> None:
    service = make_service()
    service.connected = True
    service._client = Mock()
    monkeypatch.setattr(service, "_find_code_id", lambda device_id, code: 34)
    service.publish_ha_event(RFFrame(code="ABC123", source_bridge="bridge", device_id=12, device_name="Remote", action="Open"))
    published = [call.args for call in service._client.publish.call_args_list]
    assert ("rfmanager/event/device/12/code/34", "PRESS") in [args[:2] for args in published]
    event_messages = [args for args in published if args[0] == "rfmanager/event-entity/device/12/code/34"]
    assert len(event_messages) == 1
    assert '"event_type":"press"' in event_messages[0][1]
    assert '"code":"ABC123"' in event_messages[0][1]
