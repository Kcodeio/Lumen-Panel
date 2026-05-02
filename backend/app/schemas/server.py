"""Server-related schemas."""
from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.server import ServerStatus

_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-\. ]{1,120}$")
_IMAGE_RE = re.compile(r"^[a-zA-Z0-9._/:\-]{1,255}$")


class ServerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    image: str = Field(min_length=1, max_length=255)
    memory_mb: int = Field(default=512, ge=64, le=32768)
    cpu_limit: float = Field(default=1.0, ge=0.1, le=16.0)
    env: dict[str, str] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        if not _NAME_RE.match(v):
            raise ValueError("Invalid name characters")
        return v

    @field_validator("image")
    @classmethod
    def _validate_image(cls, v: str) -> str:
        if not _IMAGE_RE.match(v):
            raise ValueError("Invalid docker image reference")
        return v

    @field_validator("env")
    @classmethod
    def _validate_env(cls, v: dict[str, str]) -> dict[str, str]:
        if len(v) > 64:
            raise ValueError("Too many env vars (max 64)")
        clean: dict[str, str] = {}
        for key, val in v.items():
            if not re.match(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$", key):
                raise ValueError(f"Invalid env key: {key}")
            if not isinstance(val, str) or len(val) > 1024:
                raise ValueError(f"Invalid env value for {key}")
            clean[key] = val
        return clean


class ServerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    memory_mb: int | None = Field(default=None, ge=64, le=32768)
    cpu_limit: float | None = Field(default=None, ge=0.1, le=16.0)
    env: dict[str, str] | None = None


class ServerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uuid: str
    name: str
    image: str
    memory_mb: int
    cpu_limit: float
    port: int
    status: ServerStatus
    container_id: str | None
    owner_id: int
    created_at: datetime
    updated_at: datetime


class ServerStatusOut(BaseModel):
    uuid: str
    status: ServerStatus
    cpu_percent: float | None = None
    memory_mb: float | None = None
    uptime_seconds: int | None = None
