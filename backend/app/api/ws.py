"""WebSocket endpoints for live log streaming."""
from __future__ import annotations

import asyncio
import json

import httpx
from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_token
from app.models.server import Server
from app.models.user import User

router = APIRouter()


def _authenticate_ws(token: str | None, db: Session) -> User | None:
    if not token:
        return None
    try:
        payload = decode_token(token)
    except Exception:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    return db.query(User).filter(User.id == int(user_id)).first()


@router.websocket("/ws/servers/{server_id}/logs")
async def stream_logs(
    websocket: WebSocket,
    server_id: int,
    token: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> None:
    """Stream live container logs from the agent to the client."""
    user = _authenticate_ws(token, db)
    if not user:
        await websocket.close(code=4401)
        return

    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        await websocket.close(code=4404)
        return
    if not user.is_admin and server.owner_id != user.id:
        await websocket.close(code=4403)
        return

    await websocket.accept()
    url = f"{settings.agent_url}/containers/{server.uuid}/logs/stream"
    headers = {"X-Node-Key": settings.node_key}

    try:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("GET", url, headers=headers) as resp:
                if resp.status_code != 200:
                    await websocket.send_text(
                        json.dumps({"error": f"agent returned {resp.status_code}"})
                    )
                    await websocket.close(code=4500)
                    return
                async for line in resp.aiter_lines():
                    if line:
                        await websocket.send_text(line)
    except WebSocketDisconnect:
        return
    except (httpx.HTTPError, asyncio.CancelledError) as exc:
        try:
            await websocket.send_text(json.dumps({"error": str(exc)}))
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
