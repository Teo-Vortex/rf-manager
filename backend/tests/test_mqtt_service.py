from unittest.mock import Mock

import pytest

from backend.app.config import Settings
from backend.app.mqtt_service import MQTTService


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


def test_publish_command_requires_connection() -> None:
    service = make_service()
    with pytest.raises(ConnectionError):
        service.publish_command("cmnd/bridge/RfCode", "#ABC123")
