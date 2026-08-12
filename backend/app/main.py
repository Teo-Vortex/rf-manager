import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import Device, RFCode, RFEvent, get_db, init_db
from .events import EventService
from .log_buffer import LogEntry, memory_log_handler
from .models import DeviceCreate, DeviceView, MQTTConfigUpdate, MQTTConfigView, MQTTStatus, RFCodeView, RFFrame, TransmitRequest, TransmitResult
from .mqtt_service import MQTTService
from .settings_store import config_view, effective_settings, save_mqtt_config
from .tasmota_adapter import UnsupportedRFCode, build_rfcode_command

settings = get_settings()
logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger().addHandler(memory_log_handler)
logger = logging.getLogger(__name__)
event_service = EventService(settings.rf_duplicate_window_ms)
mqtt_service = MQTTService(settings, event_service)


def read_version() -> str:
    for path in (Path("VERSION"), Path(__file__).resolve().parents[2] / "VERSION"):
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    return "0.0.0-dev"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    event_service.bind_loop(asyncio.get_running_loop())
    mqtt_service.settings = effective_settings(settings)
    mqtt_service._client = mqtt_service._create_client(mqtt_service.settings)
    mqtt_service.start()
    yield
    mqtt_service.stop()


app = FastAPI(title="RF Manager API", version=read_version(), lifespan=lifespan)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": read_version()}


@app.get("/api/status", response_model=MQTTStatus)
def status() -> MQTTStatus:
    active = mqtt_service.settings
    return MQTTStatus(
        connected=mqtt_service.connected,
        host=active.mqtt_host,
        port=active.mqtt_port,
        topic=active.tasmota_receive_topic,
        last_error=mqtt_service.last_error,
    )


@app.get("/api/settings/mqtt", response_model=MQTTConfigView)
def get_mqtt_config() -> MQTTConfigView:
    return config_view(settings)


@app.put("/api/settings/mqtt", response_model=MQTTStatus)
def update_mqtt_config(payload: MQTTConfigUpdate) -> MQTTStatus:
    active = save_mqtt_config(payload, settings)
    logger.info(
        "MQTT configuration updated from UI: host=%s port=%s TLS=%s client_id=%s topic=%s username_configured=%s password_configured=%s",
        active.mqtt_host,
        active.mqtt_port,
        active.mqtt_tls,
        active.mqtt_client_id,
        active.tasmota_receive_topic,
        bool(active.mqtt_username),
        bool(active.mqtt_password),
    )
    mqtt_service.reconfigure(active)
    return MQTTStatus(
        connected=False,
        host=active.mqtt_host,
        port=active.mqtt_port,
        topic=active.tasmota_receive_topic,
        last_error=None,
    )


@app.post("/api/transmit", response_model=TransmitResult)
def transmit(payload: TransmitRequest) -> TransmitResult:
    try:
        topic, command = build_rfcode_command(mqtt_service.settings.tasmota_command_topic, payload.code)
    except UnsupportedRFCode as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        message_id = mqtt_service.publish_command(topic, command)
    except ConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return TransmitResult(accepted=True, topic=topic, payload=command, message_id=message_id)


@app.post("/api/devices/{device_id}/codes/{code_id}/transmit", response_model=TransmitResult)
def transmit_saved_code(device_id: int, code_id: int, db: Session = Depends(get_db)) -> TransmitResult:
    code = db.scalar(select(RFCode).where(RFCode.id == code_id, RFCode.device_id == device_id, RFCode.enabled.is_(True)))
    if not code:
        raise HTTPException(status_code=404, detail="RF code not found")
    return transmit(TransmitRequest(code=code.code, protocol=code.protocol, bits=code.bits, pulse=code.pulse))


@app.get("/api/diagnostics/logs", response_model=list[LogEntry])
def diagnostic_logs(limit: int = 300) -> list[LogEntry]:
    return memory_log_handler.recent(min(max(limit, 1), 1000))


@app.get("/api/events", response_model=list[RFFrame])
def events(limit: int = 100, db: Session = Depends(get_db)) -> list[RFFrame]:
    rows = db.scalars(select(RFEvent).order_by(desc(RFEvent.timestamp)).limit(min(max(limit, 1), 500))).all()
    return [
        RFFrame(
            code=row.code, bits=row.bits, protocol=row.protocol, pulse=row.pulse,
            sync=row.sync, low=row.low, high=row.high, source_bridge=row.source_bridge,
            timestamp=row.timestamp, count=row.count,
        )
        for row in rows
    ]


def device_view(device: Device) -> DeviceView:
    return DeviceView(
        id=device.id, name=device.name, device_type=device.device_type, area=device.area,
        enabled=device.enabled,
        codes=[RFCodeView(id=code.id, code=code.code, action=code.action, protocol=code.protocol, bits=code.bits, pulse=code.pulse) for code in device.codes],
    )


def duplicate_assignments(db: Session, payload: DeviceCreate, exclude_device_id: int | None = None) -> list[dict[str, object]]:
    codes = {item.code.strip().upper() for item in payload.codes}
    query = select(RFCode, Device).join(Device, RFCode.device_id == Device.id).where(RFCode.code.in_(codes))
    if exclude_device_id is not None:
        query = query.where(Device.id != exclude_device_id)
    return [{"code": code.code, "device_id": device.id, "device_name": device.name, "action": code.action} for code, device in db.execute(query).all()]


def apply_device_payload(device: Device, payload: DeviceCreate) -> None:
    device.name = payload.name.strip()
    device.device_type = payload.device_type
    device.area = (payload.area or "").strip() or None
    device.updated_at = datetime.now(timezone.utc)
    device.codes.clear()
    for item in payload.codes:
        device.codes.append(RFCode(code=item.code.strip().upper(), action=item.action.strip(), protocol=item.protocol, bits=item.bits, pulse=item.pulse))


@app.get("/api/devices", response_model=list[DeviceView])
def list_devices(db: Session = Depends(get_db)) -> list[DeviceView]:
    return [device_view(device) for device in db.scalars(select(Device).order_by(Device.name)).unique().all()]


@app.post("/api/devices", response_model=DeviceView, status_code=201)
def create_device(payload: DeviceCreate, db: Session = Depends(get_db)) -> DeviceView:
    conflicts = duplicate_assignments(db, payload)
    if conflicts and not payload.allow_duplicates:
        raise HTTPException(status_code=409, detail={"message": "One or more RF codes are already assigned", "conflicts": conflicts})
    device = Device()
    apply_device_payload(device, payload)
    db.add(device)
    db.commit()
    db.refresh(device)
    logger.info("Device created: id=%s name=%s type=%s codes=%s", device.id, device.name, device.device_type, len(device.codes))
    return device_view(device)


@app.put("/api/devices/{device_id}", response_model=DeviceView)
def update_device(device_id: int, payload: DeviceCreate, db: Session = Depends(get_db)) -> DeviceView:
    device = db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    conflicts = duplicate_assignments(db, payload, exclude_device_id=device_id)
    if conflicts and not payload.allow_duplicates:
        raise HTTPException(status_code=409, detail={"message": "One or more RF codes are already assigned", "conflicts": conflicts})
    apply_device_payload(device, payload)
    db.commit()
    db.refresh(device)
    logger.info("Device updated: id=%s name=%s codes=%s", device.id, device.name, len(device.codes))
    return device_view(device)


@app.delete("/api/devices/{device_id}", status_code=204)
def delete_device(device_id: int, db: Session = Depends(get_db)) -> None:
    device = db.get(Device, device_id)
    if device:
        db.delete(device)
        db.commit()


@app.websocket("/api/ws/live")
async def live(websocket: WebSocket) -> None:
    await event_service.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        event_service.disconnect(websocket)


frontend = Path("frontend/dist")
if frontend.exists():
    app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        candidate = frontend / path
        return FileResponse(candidate if candidate.is_file() else frontend / "index.html")
