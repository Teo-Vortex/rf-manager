import asyncio
from collections.abc import Callable
from datetime import datetime, timezone

from fastapi import WebSocket

from sqlalchemy import select

from .db import Device, RFCode, RFEvent, SessionLocal
from .models import RFFrame


class EventService:
    def __init__(self, duplicate_window_ms: int) -> None:
        self._window_seconds = duplicate_window_ms / 1000
        self._recent: dict[tuple[str, str, int | None, int | None], tuple[float, int]] = {}
        self._clients: set[WebSocket] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._publisher: Callable[[RFFrame], None] | None = None

    def set_publisher(self, publisher: Callable[[RFFrame], None]) -> None:
        self._publisher = publisher

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._clients.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self._clients.discard(websocket)

    def clear_recent(self) -> None:
        self._recent.clear()

    def submit_from_mqtt_thread(self, frame: RFFrame) -> None:
        if self._loop is not None:
            asyncio.run_coroutine_threadsafe(self.process(frame), self._loop)

    async def process(self, frame: RFFrame) -> RFFrame:
        now = asyncio.get_running_loop().time()
        key = (frame.source_bridge, frame.code, frame.protocol, frame.bits)
        previous = self._recent.get(key)

        with SessionLocal() as db:
            match = db.execute(
                select(RFCode, Device)
                .join(Device, RFCode.device_id == Device.id)
                .where(RFCode.code == frame.code, RFCode.enabled.is_(True), Device.enabled.is_(True))
                .limit(1)
            ).first()
            if match:
                rf_code, device = match
                frame.device_id = device.id
                frame.device_name = device.name
                frame.action = rf_code.action

        if previous and now - previous[0] <= self._window_seconds:
            event_id = previous[1]
            with SessionLocal() as db:
                event = db.get(RFEvent, event_id)
                if event:
                    event.count += 1
                    event.timestamp = datetime.now(timezone.utc)
                    db.commit()
                    frame.count = event.count
            self._recent[key] = (now, event_id)
        else:
            with SessionLocal() as db:
                event = RFEvent(**frame.model_dump(exclude={"count"}), count=1)
                db.add(event)
                db.commit()
                db.refresh(event)
                event_id = event.id
            self._recent[key] = (now, event_id)

        await self._broadcast(frame.model_dump(mode="json"))
        if self._publisher:
            self._publisher(frame)
        return frame

    async def _broadcast(self, payload: dict[str, object]) -> None:
        dead: list[WebSocket] = []
        for client in self._clients:
            try:
                await client.send_json(payload)
            except Exception:
                dead.append(client)
        for client in dead:
            self.disconnect(client)
