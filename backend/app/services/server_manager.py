"""High-level orchestration for game servers (DB + agent)."""
from __future__ import annotations

import uuid as uuid_lib
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.server import Server, ServerStatus
from app.models.user import User
from app.schemas.server import ServerCreate, ServerUpdate
from app.services.agent_client import AgentClient, AgentClientError
from app.services.ports import allocate_port


class ServerManagerError(RuntimeError):
    """Generic server-management failure."""


def _audit(db: Session, actor: User, action: str, target: str, details: str | None = None) -> None:
    db.add(
        AuditLog(actor=actor.email, action=action, target=target, details=details)
    )


async def create_server(db: Session, owner: User, data: ServerCreate) -> Server:
    port = allocate_port(db)
    server = Server(
        uuid=str(uuid_lib.uuid4()),
        name=data.name,
        image=data.image,
        memory_mb=data.memory_mb,
        cpu_limit=data.cpu_limit,
        port=port,
        owner_id=owner.id,
        status=ServerStatus.CREATED,
    )
    server.env = data.env
    db.add(server)
    db.flush()  # get id

    agent = AgentClient()
    try:
        await agent.create_container(
            uuid=server.uuid,
            image=server.image,
            memory_mb=server.memory_mb,
            cpu_limit=server.cpu_limit,
            host_port=server.port,
            env=server.env,
        )
    except AgentClientError as exc:
        db.rollback()
        raise ServerManagerError(f"Agent failed to create container: {exc}") from exc

    _audit(db, owner, "server.create", server.uuid, f"name={server.name}")
    db.commit()
    db.refresh(server)
    return server


async def start_server(db: Session, actor: User, server: Server) -> Server:
    server.status = ServerStatus.STARTING
    db.commit()

    agent = AgentClient()
    try:
        result: dict[str, Any] = await agent.start_container(server.uuid)
    except AgentClientError as exc:
        server.status = ServerStatus.ERROR
        db.commit()
        raise ServerManagerError(str(exc)) from exc

    server.container_id = result.get("container_id") or server.container_id
    server.status = ServerStatus.RUNNING
    _audit(db, actor, "server.start", server.uuid)
    db.commit()
    db.refresh(server)
    return server


async def stop_server(db: Session, actor: User, server: Server) -> Server:
    server.status = ServerStatus.STOPPING
    db.commit()

    agent = AgentClient()
    try:
        await agent.stop_container(server.uuid)
    except AgentClientError as exc:
        server.status = ServerStatus.ERROR
        db.commit()
        raise ServerManagerError(str(exc)) from exc

    server.status = ServerStatus.STOPPED
    _audit(db, actor, "server.stop", server.uuid)
    db.commit()
    db.refresh(server)
    return server


async def delete_server(db: Session, actor: User, server: Server) -> None:
    agent = AgentClient()
    try:
        await agent.remove_container(server.uuid)
    except AgentClientError:
        # Container might already be gone; we'll still drop the DB record.
        pass
    _audit(db, actor, "server.delete", server.uuid, f"name={server.name}")
    db.delete(server)
    db.commit()


def update_server(db: Session, actor: User, server: Server, data: ServerUpdate) -> Server:
    if data.name is not None:
        server.name = data.name
    if data.memory_mb is not None:
        server.memory_mb = data.memory_mb
    if data.cpu_limit is not None:
        server.cpu_limit = data.cpu_limit
    if data.env is not None:
        server.env = data.env
    _audit(db, actor, "server.update", server.uuid)
    db.commit()
    db.refresh(server)
    return server
