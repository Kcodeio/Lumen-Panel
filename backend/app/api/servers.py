"""Server (game server) management endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.server import Server
from app.models.user import User
from app.schemas.server import (
    ServerCreate,
    ServerOut,
    ServerStatusOut,
    ServerUpdate,
)
from app.services.agent_client import AgentClient, AgentClientError
from app.services.ports import NoFreePortError
from app.services.server_manager import (
    ServerManagerError,
    create_server,
    delete_server,
    start_server,
    stop_server,
    update_server,
)

router = APIRouter()


def _get_server_or_404(db: Session, server_id: int, user: User) -> Server:
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    if not user.is_admin and server.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized for this server")
    return server


@router.get("", response_model=list[ServerOut])
def list_servers(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> list[ServerOut]:
    query = db.query(Server)
    if not current.is_admin:
        query = query.filter(Server.owner_id == current.id)
    return [ServerOut.model_validate(s) for s in query.order_by(Server.id.desc()).all()]


@router.post("", response_model=ServerOut, status_code=status.HTTP_201_CREATED)
async def create(
    payload: ServerCreate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> ServerOut:
    try:
        server = await create_server(db, current, payload)
    except NoFreePortError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ServerManagerError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ServerOut.model_validate(server)


@router.get("/{server_id}", response_model=ServerOut)
def get_server(
    server_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> ServerOut:
    server = _get_server_or_404(db, server_id, current)
    return ServerOut.model_validate(server)


@router.patch("/{server_id}", response_model=ServerOut)
def update(
    server_id: int,
    payload: ServerUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> ServerOut:
    server = _get_server_or_404(db, server_id, current)
    server = update_server(db, current, server, payload)
    return ServerOut.model_validate(server)


@router.post("/{server_id}/start", response_model=ServerOut)
async def start(
    server_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> ServerOut:
    server = _get_server_or_404(db, server_id, current)
    try:
        server = await start_server(db, current, server)
    except ServerManagerError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ServerOut.model_validate(server)


@router.post("/{server_id}/stop", response_model=ServerOut)
async def stop(
    server_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> ServerOut:
    server = _get_server_or_404(db, server_id, current)
    try:
        server = await stop_server(db, current, server)
    except ServerManagerError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ServerOut.model_validate(server)


@router.delete("/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(
    server_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> None:
    server = _get_server_or_404(db, server_id, current)
    await delete_server(db, current, server)


@router.get("/{server_id}/status", response_model=ServerStatusOut)
async def server_status(
    server_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> ServerStatusOut:
    server = _get_server_or_404(db, server_id, current)
    agent = AgentClient()
    try:
        info = await agent.container_status(server.uuid)
    except AgentClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ServerStatusOut(
        uuid=server.uuid,
        status=server.status,
        cpu_percent=info.get("cpu_percent"),
        memory_mb=info.get("memory_mb"),
        uptime_seconds=info.get("uptime_seconds"),
    )


@router.get("/{server_id}/logs")
async def server_logs(
    server_id: int,
    tail: int = 200,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict[str, str]:
    server = _get_server_or_404(db, server_id, current)
    agent = AgentClient()
    try:
        logs = await agent.container_logs(server.uuid, tail=tail)
    except AgentClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"uuid": server.uuid, "logs": logs}
