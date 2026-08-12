from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "RF Manager"
    database_url: str = "sqlite:///./data/rfmanager.db"
    mqtt_host: str = "host.docker.internal"
    mqtt_port: int = 1883
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    mqtt_tls: bool = False
    mqtt_client_id: str = "rf-manager"
    mqtt_keepalive: int = 60
    tasmota_receive_topic: str = "tele/+/RESULT"
    tasmota_command_topic: str = "cmnd/rfbridge/"
    ha_enabled: bool = True
    ha_discovery_prefix: str = "homeassistant"
    ha_base_topic: str = "rfmanager"
    rf_duplicate_window_ms: int = Field(default=300, ge=0, le=60_000)
    rf_event_retention_days: int = Field(default=30, ge=1)
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
