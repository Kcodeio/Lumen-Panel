"""Allocate host ports for game servers from the configured range."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.server import Server


class NoFreePortError(RuntimeError):
    """Raised when the configured port range is exhausted."""


def allocate_port(db: Session) -> int:
    """Return the lowest unused port in the configured range."""
    used = {row.port for row in db.query(Server.port).all()}
    for candidate in range(settings.game_port_start, settings.game_port_end + 1):
        if candidate not in used:
            return candidate
    raise NoFreePortError(
        f"No free ports between {settings.game_port_start} and {settings.game_port_end}"
    )
