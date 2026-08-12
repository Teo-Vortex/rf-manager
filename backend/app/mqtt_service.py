import logging
import json
import random
import socket
import threading
import time

import paho.mqtt.client as mqtt

from .config import Settings
from .events import EventService
from .home_assistant import resolve_command, sync_discovery
from .tasmota import TasmotaParseError, parse_tasmota_message
from .tasmota_adapter import build_rfcode_command

logger = logging.getLogger(__name__)


class MQTTService:
    def __init__(self, settings: Settings, event_service: EventService) -> None:
        self.settings = settings
        self.event_service = event_service
        self.connected = False
        self.last_error: str | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._attempt = 0
        self._client = self._create_client(settings)
        self.event_service.set_publisher(self.publish_ha_event)

    def _create_client(self, settings: Settings) -> mqtt.Client:
        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=settings.mqtt_client_id,
        )
        if settings.mqtt_username:
            client.username_pw_set(settings.mqtt_username, settings.mqtt_password)
        if settings.mqtt_tls:
            client.tls_set()
        client.will_set(f"{settings.ha_base_topic}/status", "offline", qos=1, retain=True)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        client.on_subscribe = self._on_subscribe
        return client

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="mqtt", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._client.disconnect()
        if self._thread:
            self._thread.join(timeout=5)

    def reconfigure(self, settings: Settings) -> None:
        self.stop()
        self.settings = settings
        self.connected = False
        self.last_error = None
        self._stop = threading.Event()
        self._client = self._create_client(settings)
        self.start()

    def publish_command(self, topic: str, payload: str) -> int:
        if not self.connected:
            raise ConnectionError("MQTT is not connected")
        info = self._client.publish(topic, payload, qos=0, retain=False)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise ConnectionError(f"MQTT publish failed with result {info.rc}")
        logger.info("MQTT command published: topic=%s payload=%s mid=%s", topic, payload, info.mid)
        return info.mid

    def sync_home_assistant(self) -> int:
        if not self.connected:
            raise ConnectionError("MQTT is not connected")
        return sync_discovery(self._client, self.settings)

    def publish_ha_event(self, frame: object) -> None:
        if not self.connected or not self.settings.ha_enabled:
            return
        payload = frame.model_dump(mode="json")
        self._client.publish(
            f"{self.settings.ha_base_topic}/event",
            json.dumps(payload, separators=(",", ":")),
            qos=0,
            retain=False,
        )
        if frame.device_id is not None:
            from .home_assistant import event_state_topic, trigger_topic

            code_id = self._find_code_id(frame.device_id, frame.code)
            if code_id is not None:
                self._client.publish(
                    trigger_topic(self.settings, frame.device_id, code_id),
                    "PRESS",
                    qos=0,
                    retain=False,
                )
                self._client.publish(
                    event_state_topic(self.settings, frame.device_id, code_id),
                    json.dumps(
                        {
                            "event_type": "press",
                            "code": frame.code,
                            "action": frame.action,
                            "device_name": frame.device_name,
                            "source_bridge": frame.source_bridge,
                            "timestamp": frame.timestamp.isoformat(),
                        },
                        separators=(",", ":"),
                    ),
                    qos=0,
                    retain=False,
                )

    @staticmethod
    def _find_code_id(device_id: int, code: str) -> int | None:
        from sqlalchemy import select

        from .db import RFCode, SessionLocal

        with SessionLocal() as db:
            return db.scalar(
                select(RFCode.id).where(
                    RFCode.device_id == device_id,
                    RFCode.code == code,
                    RFCode.enabled.is_(True),
                ).limit(1)
            )

    def _run(self) -> None:
        delay = 1.0
        while not self._stop.is_set():
            self._attempt += 1
            started = time.monotonic()
            try:
                addresses = sorted({
                    item[4][0]
                    for item in socket.getaddrinfo(
                        self.settings.mqtt_host, self.settings.mqtt_port, type=socket.SOCK_STREAM
                    )
                })
                logger.info(
                    "MQTT attempt %s: %s:%s (resolved: %s, TLS: %s, client ID: %s)",
                    self._attempt,
                    self.settings.mqtt_host,
                    self.settings.mqtt_port,
                    ", ".join(addresses),
                    self.settings.mqtt_tls,
                    self.settings.mqtt_client_id,
                )
                self._client.connect(
                    self.settings.mqtt_host,
                    self.settings.mqtt_port,
                    self.settings.mqtt_keepalive,
                )
                self._client.loop_forever()
                delay = 1.0
            except Exception as exc:
                self.connected = False
                elapsed = time.monotonic() - started
                self.last_error = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "MQTT attempt %s failed after %.2fs: %s: %s",
                    self._attempt,
                    elapsed,
                    type(exc).__name__,
                    exc,
                )
            if not self._stop.is_set():
                wait = delay + random.uniform(0, delay * 0.2)
                logger.info("MQTT reconnect scheduled in %.1fs", wait)
                time.sleep(wait)
                delay = min(delay * 2, 60)

    def _on_connect(self, client: mqtt.Client, userdata: object, flags: object, reason_code: object, properties: object) -> None:
        is_failure = bool(getattr(reason_code, "is_failure", reason_code != 0))
        if not is_failure:
            self.connected = True
            self.last_error = None
            result, message_id = client.subscribe(self.settings.tasmota_receive_topic)
            if self.settings.ha_enabled:
                client.subscribe(f"{self.settings.ha_base_topic}/command/#")
            client.publish(f"{self.settings.ha_base_topic}/status", "online", qos=1, retain=True)
            sync_discovery(client, self.settings)
            logger.info(
                "MQTT connected successfully; subscribing to %s (result=%s, mid=%s)",
                self.settings.tasmota_receive_topic,
                result,
                message_id,
            )
        else:
            self.last_error = f"Connection rejected: {reason_code}"
            logger.error("MQTT broker rejected connection: %s", reason_code)

    def _on_disconnect(self, client: mqtt.Client, userdata: object, disconnect_flags: object, reason_code: object, properties: object) -> None:
        self.connected = False
        if not self._stop.is_set():
            self.last_error = f"Disconnected: {reason_code}"
            logger.warning("MQTT disconnected: %s", reason_code)

    def _on_subscribe(self, client: mqtt.Client, userdata: object, mid: int, reason_code_list: list[object], properties: object) -> None:
        failures = [code for code in reason_code_list if bool(getattr(code, "is_failure", False))]
        if failures:
            self.last_error = f"MQTT subscription rejected: {', '.join(map(str, failures))}"
            logger.error("MQTT subscription rejected by broker: mid=%s reasons=%s", mid, reason_code_list)
        else:
            logger.info("MQTT subscription confirmed by broker: mid=%s granted=%s", mid, reason_code_list)

    def _on_message(self, client: mqtt.Client, userdata: object, message: mqtt.MQTTMessage) -> None:
        try:
            command = resolve_command(message.topic, message.payload, self.settings)
            if command:
                topic, payload = build_rfcode_command(self.settings.tasmota_command_topic, command.code)
                self.publish_command(topic, payload)
                logger.info("Home Assistant command sent: device_id=%s code_id=%s", command.device_id, command.id)
                return
            frame = parse_tasmota_message(message.topic, message.payload)
            if frame:
                self.event_service.submit_from_mqtt_thread(frame)
        except TasmotaParseError as exc:
            logger.warning("Ignored malformed Tasmota message on %s: %s", message.topic, exc)
