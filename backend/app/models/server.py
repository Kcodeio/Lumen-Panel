"""Game server ORM model."""
from __future__ import annotations

import enum
import json
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ServerStatus(str, enum.Enum):
    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class Server(Base):
    __tablename__ = "servers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    image: Mapped[str] = mapped_column(String(255), nullable=False)
    memory_mb: Mapped[int] = mapped_column(Integer, default=512, nullable=False)
    cpu_limit: Mapped[float] = mapped_column(Integer, default=1, nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    env_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    container_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[ServerStatus] = mapped_column(
        Enum(ServerStatus, native_enum=False, length=20),
        default=ServerStatus.CREATED,
        nullable=False,
    )
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    @property
    def env(self) -> dict[str, str]:
        try:
            return json.loads(self.env_json or "{}")
        except json.JSONDecodeError:
            return {}

    @env.setter
    def env(self, value: dict[str, str]) -> None:
        self.env_json = json.dumps(value or {})

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Server id={self.id} name={self.name!r} status={self.status}>"
