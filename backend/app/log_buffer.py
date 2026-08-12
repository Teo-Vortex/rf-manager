import logging
import threading
from collections import deque
from datetime import datetime, timezone

from pydantic import BaseModel


class LogEntry(BaseModel):
    timestamp: datetime
    level: str
    logger: str
    message: str


class MemoryLogHandler(logging.Handler):
    def __init__(self, capacity: int = 1000) -> None:
        super().__init__()
        self._entries: deque[LogEntry] = deque(maxlen=capacity)
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = LogEntry(
                timestamp=datetime.fromtimestamp(record.created, timezone.utc),
                level=record.levelname,
                logger=record.name,
                message=record.getMessage(),
            )
            with self._lock:
                self._entries.append(entry)
        except Exception:
            self.handleError(record)

    def recent(self, limit: int = 300) -> list[LogEntry]:
        with self._lock:
            return list(self._entries)[-limit:]


memory_log_handler = MemoryLogHandler()
