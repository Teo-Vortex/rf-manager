from sqlalchemy import select

from .config import Settings
from .db import AppSetting, SessionLocal
from .models import MQTTConfigUpdate, MQTTConfigView

MQTT_KEYS = {
    "host": "mqtt_host",
    "port": "mqtt_port",
    "username": "mqtt_username",
    "password": "mqtt_password",
    "tls": "mqtt_tls",
    "client_id": "mqtt_client_id",
    "receive_topic": "tasmota_receive_topic",
}


def _values() -> dict[str, str]:
    with SessionLocal() as db:
        return {row.key: row.value for row in db.scalars(select(AppSetting)).all()}


def effective_settings(defaults: Settings) -> Settings:
    stored = _values()
    updates: dict[str, object] = {}
    for field, key in MQTT_KEYS.items():
        if key not in stored:
            continue
        value: object = stored[key]
        if field == "port":
            value = int(value)
        elif field == "tls":
            value = value.lower() == "true"
        updates[key] = value or None if field in {"username", "password"} else value
    return defaults.model_copy(update=updates)


def config_view(defaults: Settings) -> MQTTConfigView:
    active = effective_settings(defaults)
    return MQTTConfigView(
        host=active.mqtt_host,
        port=active.mqtt_port,
        username=active.mqtt_username,
        password_configured=bool(active.mqtt_password),
        tls=active.mqtt_tls,
        client_id=active.mqtt_client_id,
        receive_topic=active.tasmota_receive_topic,
    )


def save_mqtt_config(payload: MQTTConfigUpdate, defaults: Settings) -> Settings:
    current = effective_settings(defaults)
    entries = {
        "mqtt_host": payload.host.strip(),
        "mqtt_port": str(payload.port),
        "mqtt_username": (payload.username or "").strip(),
        "mqtt_tls": str(payload.tls).lower(),
        "mqtt_client_id": payload.client_id.strip(),
        "tasmota_receive_topic": payload.receive_topic.strip(),
    }
    if payload.clear_password:
        entries["mqtt_password"] = ""
    elif payload.password is not None and payload.password != "":
        entries["mqtt_password"] = payload.password
    elif current.mqtt_password and "mqtt_password" not in entries:
        pass

    with SessionLocal() as db:
        for key, value in entries.items():
            item = db.get(AppSetting, key)
            if item:
                item.value = value
            else:
                db.add(AppSetting(key=key, value=value))
        db.commit()
    return effective_settings(defaults)
