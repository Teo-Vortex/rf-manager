from datetime import datetime, timezone

from pydantic import BaseModel, Field


class RFFrame(BaseModel):
    code: str = Field(min_length=1, max_length=128)
    bits: int | None = None
    protocol: int | None = None
    pulse: int | None = None
    sync: int | None = None
    low: int | None = None
    high: int | None = None
    source_bridge: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    count: int = 1
    device_id: int | None = None
    device_name: str | None = None
    action: str | None = None


class MQTTStatus(BaseModel):
    connected: bool
    host: str
    port: int
    topic: str
    last_error: str | None = None


class MQTTConfigView(BaseModel):
    host: str
    port: int
    username: str | None = None
    password_configured: bool = False
    tls: bool = False
    client_id: str
    receive_topic: str


class MQTTConfigUpdate(BaseModel):
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=1883, ge=1, le=65535)
    username: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, max_length=1024)
    clear_password: bool = False
    tls: bool = False
    client_id: str = Field(default="rf-manager", min_length=1, max_length=255)
    receive_topic: str = Field(default="tele/+/RESULT", min_length=1, max_length=512)


class RFCodeCreate(BaseModel):
    code: str = Field(min_length=1, max_length=128)
    action: str = Field(min_length=1, max_length=255)
    protocol: int | None = None
    bits: int | None = None
    pulse: int | None = None


class DeviceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    device_type: str = "remote_control"
    area: str | None = Field(default=None, max_length=255)
    codes: list[RFCodeCreate] = Field(min_length=1)


class RFCodeView(RFCodeCreate):
    id: int


class DeviceView(BaseModel):
    id: int
    name: str
    device_type: str
    area: str | None
    enabled: bool
    codes: list[RFCodeView]
