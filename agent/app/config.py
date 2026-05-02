"""Configuration for the node agent."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LUMEN_", extra="ignore")

    node_key: str = Field(default="dev-node-key")
    agent_port: int = Field(default=8081)
    panel_url: str = Field(default="http://127.0.0.1:8000")
    data_dir: str = Field(default="/var/lib/lumen")
    log_dir: str = Field(default="/var/log/lumen")

    container_label: str = "com.lumen.managed"
    container_prefix: str = "lumen-"

    @property
    def data_path(self) -> Path:
        p = Path(self.data_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def log_path(self) -> Path:
        p = Path(self.log_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache(maxsize=1)
def get_settings() -> AgentSettings:
    return AgentSettings()


settings = get_settings()
