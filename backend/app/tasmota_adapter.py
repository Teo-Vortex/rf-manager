import re


class UnsupportedRFCode(ValueError):
    pass


def normalize_command_base(topic: str) -> str:
    return topic.strip().rstrip("/")


def build_rfcode_command(command_topic: str, code: str) -> tuple[str, str]:
    normalized = code.strip().upper()
    if normalized.startswith("0X"):
        normalized = normalized[2:]
    if not re.fullmatch(r"[0-9A-F]{6}", normalized):
        raise UnsupportedRFCode("Standard Tasmota RfCode transmission requires exactly 6 hexadecimal characters")
    return f"{normalize_command_base(command_topic)}/RfCode", f"#{normalized}"
