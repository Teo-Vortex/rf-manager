import json
import logging
import re

from sqlalchemy import select

from .config import Settings
from .db import AppSetting, Device, RFCode, SessionLocal

logger = logging.getLogger(__name__)
COMMAND_RE = re.compile(r"^(.+)/command/device/(\d+)/code/(\d+)/set$")
MANIFEST_KEY = "ha_discovery_manifest"


def discovery_topic(settings: Settings, device_id: int, code_id: int) -> str:
    return f"{settings.ha_discovery_prefix}/button/rfmanager_{device_id}_{code_id}/config"


def trigger_discovery_topic(settings: Settings, device_id: int, code_id: int) -> str:
    return f"{settings.ha_discovery_prefix}/device_automation/rfmanager_{device_id}/button_{code_id}/config"


def trigger_topic(settings: Settings, device_id: int, code_id: int) -> str:
    return f"{settings.ha_base_topic}/event/device/{device_id}/code/{code_id}"


def command_topic(settings: Settings, device_id: int, code_id: int) -> str:
    return f"{settings.ha_base_topic}/command/device/{device_id}/code/{code_id}/set"


def discovery_payload(settings: Settings, device: Device, code: RFCode) -> str:
    payload: dict[str, object] = {
        "name": code.action,
        "unique_id": f"rfmanager_{device.id}_{code.id}",
        "command_topic": command_topic(settings, device.id, code.id),
        "payload_press": "PRESS",
        "availability_topic": f"{settings.ha_base_topic}/status",
        "payload_available": "online",
        "payload_not_available": "offline",
        "device": {
            "identifiers": [f"rfmanager_device_{device.id}"],
            "name": device.name,
            "manufacturer": "RF Manager",
            "model": "Tasmota RF device",
        },
    }
    if device.area:
        payload["suggested_area"] = device.area
    return json.dumps(payload, separators=(",", ":"))


def trigger_discovery_payload(settings: Settings, device: Device, code: RFCode, subtype: str | None = None) -> str:
    payload: dict[str, object] = {
        "automation_type": "trigger",
        "type": "button_short_press",
        "subtype": subtype or code.action,
        "payload": "PRESS",
        "topic": trigger_topic(settings, device.id, code.id),
        "device": {
            "identifiers": [f"rfmanager_device_{device.id}"],
            "name": device.name,
            "manufacturer": "RF Manager",
            "model": "Tasmota RF device",
        },
    }
    return json.dumps(payload, separators=(",", ":"))


def sync_discovery(client: object, settings: Settings) -> int:
    if not settings.ha_enabled:
        return clear_discovery(client)
    current: set[str] = set()
    with SessionLocal() as db:
        devices = db.scalars(select(Device).where(Device.enabled.is_(True))).unique().all()
        for device in devices:
            action_counts: dict[str, int] = {}
            for item in device.codes:
                action_counts[item.action] = action_counts.get(item.action, 0) + 1
            for code in device.codes:
                if not code.enabled:
                    continue
                topic = discovery_topic(settings, device.id, code.id)
                client.publish(topic, discovery_payload(settings, device, code), qos=1, retain=True)
                current.add(topic)
                trigger_config_topic = trigger_discovery_topic(settings, device.id, code.id)
                subtype = code.action if action_counts[code.action] == 1 else f"{code.action} {code.id}"
                client.publish(
                    trigger_config_topic,
                    trigger_discovery_payload(settings, device, code, subtype),
                    qos=1,
                    retain=True,
                )
                current.add(trigger_config_topic)
        previous = _manifest(db)
        for stale_topic in previous - current:
            client.publish(stale_topic, "", qos=1, retain=True)
        _save_manifest(db, current)
    logger.info("Home Assistant discovery synchronized: %s discovery entries", len(current))
    return len(current)


def clear_discovery(client: object) -> int:
    with SessionLocal() as db:
        previous = _manifest(db)
        for topic in previous:
            client.publish(topic, "", qos=1, retain=True)
        _save_manifest(db, set())
    return len(previous)


def resolve_command(topic: str, payload: bytes, settings: Settings) -> RFCode | None:
    match = COMMAND_RE.match(topic)
    if not match or match.group(1) != settings.ha_base_topic:
        return None
    if payload.decode("utf-8", errors="ignore").strip().upper() != "PRESS":
        return None
    device_id, code_id = int(match.group(2)), int(match.group(3))
    with SessionLocal() as db:
        return db.scalar(
            select(RFCode)
            .join(Device, RFCode.device_id == Device.id)
            .where(RFCode.id == code_id, RFCode.device_id == device_id, RFCode.enabled.is_(True), Device.enabled.is_(True))
        )


def _manifest(db: object) -> set[str]:
    row = db.get(AppSetting, MANIFEST_KEY)
    if not row:
        return set()
    try:
        return set(json.loads(row.value))
    except (TypeError, ValueError):
        return set()


def _save_manifest(db: object, topics: set[str]) -> None:
    value = json.dumps(sorted(topics))
    row = db.get(AppSetting, MANIFEST_KEY)
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=MANIFEST_KEY, value=value))
    db.commit()
