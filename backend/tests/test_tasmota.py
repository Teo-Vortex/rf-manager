import pytest

from backend.app.tasmota import TasmotaParseError, parse_tasmota_message


def test_parses_modern_tasmota_frame() -> None:
    frame = parse_tasmota_message(
        "tele/rfbridge/RESULT",
        b'{"RfReceived":{"Data":"abc123","Bits":24,"Protocol":1,"Pulse":350}}',
    )
    assert frame is not None
    assert frame.code == "ABC123"
    assert frame.bits == 24
    assert frame.protocol == 1
    assert frame.pulse == 350
    assert frame.source_bridge == "rfbridge"


def test_parses_legacy_tasmota_frame_with_missing_fields() -> None:
    frame = parse_tasmota_message(
        "tele/garage_bridge/RESULT",
        '{"RfReceived":{"Sync":12340,"Low":390,"High":1170,"Data":"FF22A1"}}',
    )
    assert frame is not None
    assert frame.sync == 12340
    assert frame.bits is None


def test_ignores_non_rf_result() -> None:
    assert parse_tasmota_message("tele/rfbridge/RESULT", '{"POWER":"ON"}') is None


def test_rejects_invalid_json() -> None:
    with pytest.raises(TasmotaParseError):
        parse_tasmota_message("tele/rfbridge/RESULT", "not-json")


def test_rejects_rf_frame_without_data() -> None:
    with pytest.raises(TasmotaParseError):
        parse_tasmota_message("tele/rfbridge/RESULT", '{"RfReceived":{"Bits":24}}')


def test_parses_real_tasmota_sensors_payload() -> None:
    frame = parse_tasmota_message(
        "tele/tasmota_A3F90F/RESULT",
        b'{"Time":"2026-08-12T18:29:08","RfReceived":{"Sync":12324,"Low":440,"High":1212,"Data":"F6A948","RfKey":"None"}}',
    )
    assert frame is not None
    assert frame.code == "F6A948"
    assert frame.source_bridge == "tasmota_A3F90F"
    assert frame.sync == 12324
