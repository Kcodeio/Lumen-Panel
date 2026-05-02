"""Application configuration loaded from environment."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings sourced from environment variables (panel.env)."""

    model_config = SettingsConfigDict(env_prefix="LUMEN_", extra="ignore")

    jwt_secret: str = Field(default="dev-insecure-change-me")
    api_key: str = Field(default="dev-api-key")
    node_key: str = Field(default="dev-node-key")
    database_url: str = Field(default="sqlite:///./lumen.db")
    data_dir: str = Field(default="./data")
    log_dir: str = Field(default="./logs")
    port: int = Field(default=8000)
    agent_url: str = Field(default="http://127.0.0.1:8081")
    game_port_start: int = Field(default=25565)
    game_port_end: int = Field(default=25600)

    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24

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
def get_settings() -> Settings:
    return Settings()


# Convenience singleton
settings = get_settings()
