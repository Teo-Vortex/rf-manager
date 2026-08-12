import asyncio
from datetime import datetime, timezone

from fastapi import WebSocket

from .db import RFEvent, SessionLocal
from .models import RFFrame


class EventService:
    def __init__(self, duplicate_window_ms: int) -> None:
        self._window_seconds = duplicate_window_ms / 1000
        self._recent: dict[tuple[str, str, int | None, int | None], tuple[float, int]] = {}
        self._clients: set[WebSocket] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._clients.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self._clients.discard(websocket)

    def submit_from_mqtt_thread(self, frame: RFFrame) -> None:
        if self._loop is not None:
            asyncio.run_coroutine_threadsafe(self.process(frame), self._loop)

    async def process(self, frame: RFFrame) -> RFFrame:
        now = asyncio.get_running_loop().time()
        key = (frame.source_bridge, frame.code, frame.protocol, frame.bits)
        previous = self._recent.get(key)

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
