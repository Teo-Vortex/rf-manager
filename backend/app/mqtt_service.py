import logging
import random
import socket
import threading
import time

import paho.mqtt.client as mqtt

from .config import Settings
from .events import EventService
from .tasmota import TasmotaParseError, parse_tasmota_message

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

    def _create_client(self, settings: Settings) -> mqtt.Client:
        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=settings.mqtt_client_id,
        )
        if settings.mqtt_username:
            client.username_pw_set(settings.mqtt_username, settings.mqtt_password)
        if settings.mqtt_tls:
            client.tls_set()
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
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
        if int(reason_code) == 0:
            self.connected = True
            self.last_error = None
            result, message_id = client.subscribe(self.settings.tasmota_receive_topic)
            client.publish("rfmanager/status", "online", qos=1, retain=True)
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

    def _on_message(self, client: mqtt.Client, userdata: object, message: mqtt.MQTTMessage) -> None:
        try:
            frame = parse_tasmota_message(message.topic, message.payload)
            if frame:
                self.event_service.submit_from_mqtt_thread(frame)
        except TasmotaParseError as exc:
            logger.warning("Ignored malformed Tasmota message on %s: %s", message.topic, exc)
