import json
from typing import Any

from .models import RFFrame


class TasmotaParseError(ValueError):
    pass


def bridge_from_topic(topic: str) -> str:
    parts = topic.split("/")
    return parts[1] if len(parts) >= 3 and parts[0] == "tele" else "unknown"


def _optional_int(data: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = data.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
    return None


def parse_tasmota_message(topic: str, payload: bytes | str) -> RFFrame | None:
    try:
        raw = payload.decode("utf-8") if isinstance(payload, bytes) else payload
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
        raise TasmotaParseError("Payload is not valid UTF-8 JSON") from exc

    received = document.get("RfReceived") if isinstance(document, dict) else None
    if not isinstance(received, dict):
        return None

    code = received.get("Data")
    if code is None or str(code).strip() == "":
        raise TasmotaParseError("RfReceived does not contain Data")

    return RFFrame(
        code=str(code).strip().upper(),
        bits=_optional_int(received, "Bits"),
        protocol=_optional_int(received, "Protocol"),
        pulse=_optional_int(received, "Pulse"),
        sync=_optional_int(received, "Sync"),
        low=_optional_int(received, "Low"),
        high=_optional_int(received, "High"),
        source_bridge=bridge_from_topic(topic),
    )
