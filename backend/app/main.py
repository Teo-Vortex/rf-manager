import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import RFEvent, get_db, init_db
from .events import EventService
from .models import MQTTConfigUpdate, MQTTConfigView, MQTTStatus, RFFrame
from .mqtt_service import MQTTService
from .settings_store import config_view, effective_settings, save_mqtt_config

settings = get_settings()
logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
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
    mqtt_service.reconfigure(active)
    return MQTTStatus(
        connected=False,
        host=active.mqtt_host,
        port=active.mqtt_port,
        topic=active.tasmota_receive_topic,
        last_error=None,
    )


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
