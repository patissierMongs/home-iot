"""환경 변수 기반 설정."""
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Home Assistant
    ha_url: str = "http://localhost:8123"
    ha_token: str = Field(..., description="HA long-lived access token")

    # MQTT
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883

    # Ollama
    ollama_url: str = "http://localhost:11434"
    ollama_main_model: str = "nemotron-cascade-2"
    ollama_embed_model: str = "bge-m3"

    # InfluxDB
    influx_url: str = "http://localhost:8086"
    influx_token: str = ""
    influx_org: str = "home"
    influx_bucket: str = "home-iot"

    # Logging
    log_level: str = "INFO"


settings = Settings()
