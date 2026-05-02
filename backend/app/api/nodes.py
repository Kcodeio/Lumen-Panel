"""Endpoints called by the node agent to register / heartbeat / report."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import verify_node_key
from app.models.server import Server, ServerStatus

router = APIRouter()


class NodeRegister(BaseModel):
    hostname: str
    agent_version: str
    docker_version: str | None = None


class NodeHeartbeat(BaseModel):
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    running_containers: int


class ContainerEvent(BaseModel):
    uuid: str
    status: str  # one of ServerStatus values
    container_id: str | None = None


@router.post("/register")
def register_node(
    body: NodeRegister,
    _: bool = Depends(verify_node_key),
) -> dict[str, str]:
    return {
        "status": "registered",
        "hostname": body.hostname,
        "server_time": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/heartbeat")
def heartbeat(body: NodeHeartbeat, _: bool = Depends(verify_node_key)) -> dict[str, str]:
    return {"status": "ok", "received_at": datetime.now(timezone.utc).isoformat()}


@router.post("/event")
def container_event(
    body: ContainerEvent,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_node_key),
) -> dict[str, str]:
    """Receive container state changes from the agent."""
    server = db.query(Server).filter(Server.uuid == body.uuid).first()
    if not server:
        raise HTTPException(status_code=404, detail="Unknown server uuid")

    try:
        server.status = ServerStatus(body.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid status: {body.status}") from exc

    if body.container_id is not None:
        server.container_id = body.container_id
    db.commit()
    return {"status": "ok"}
