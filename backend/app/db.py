from collections.abc import Generator
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


class RFEvent(Base):
    __tablename__ = "rf_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    code: Mapped[str] = mapped_column(String(128), index=True)
    bits: Mapped[int | None]
    protocol: Mapped[int | None]
    pulse: Mapped[int | None]
    sync: Mapped[int | None]
    low: Mapped[int | None]
    high: Mapped[int | None]
    source_bridge: Mapped[str] = mapped_column(String(128), index=True)
    count: Mapped[int] = mapped_column(default=1)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


engine = create_engine(get_settings().database_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
