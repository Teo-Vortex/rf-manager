import pytest

from backend.app.tasmota_adapter import UnsupportedRFCode, build_rfcode_command


def test_builds_standard_tasmota_rfcode_command() -> None:
    assert build_rfcode_command("cmnd/tasmota_A3F90F/", "abc123") == (
        "cmnd/tasmota_A3F90F/RfCode",
        "#ABC123",
    )


@pytest.mark.parametrize("code", ["ABC12", "ABC1234", "GHI123", "not-a-code"])
def test_rejects_codes_not_supported_by_standard_rfcode(code: str) -> None:
    with pytest.raises(UnsupportedRFCode):
        build_rfcode_command("cmnd/bridge", code)
