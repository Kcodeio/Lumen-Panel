"""Lumen Node Agent - FastAPI application."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app import __version__
from app.config import settings
from app.docker_manager import DockerError, get_docker_manager
from app.heartbeat import heartbeat_loop, register_with_panel
from app.security import verify_node_key

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log_file = Path(settings.log_dir) / "agent.app.log"
log_file.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_file, encoding="utf-8"),
    ],
)
logger = logging.getLogger("lumen.agent")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class CreateContainerBody(BaseModel):
    uuid: str = Field(min_length=1, max_length=64)
    image: str = Field(min_length=1, max_length=255)
    memory_mb: int = Field(ge=64, le=32768)
    cpu_limit: float = Field(ge=0.1, le=16.0)
    host_port: int = Field(ge=1, le=65535)
    env: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Lumen Agent %s starting", __version__)
    # Eagerly init docker manager so we fail fast if docker is unavailable
    try:
        get_docker_manager()
    except DockerError as exc:
        logger.error("Docker init failed: %s", exc)
    asyncio.create_task(register_with_panel())
    hb_task = asyncio.create_task(heartbeat_loop())
    try:
        yield
    finally:
        hb_task.cancel()


app = FastAPI(title="Lumen Node Agent", version=__version__, lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


# ---------------------------------------------------------------------------
# Container endpoints
# ---------------------------------------------------------------------------
@app.post("/containers", dependencies=[Depends(verify_node_key)])
async def create_container(body: CreateContainerBody):
    try:
        return await get_docker_manager().create(
            uuid=body.uuid,
            image=body.image,
            memory_mb=body.memory_mb,
            cpu_limit=body.cpu_limit,
            host_port=body.host_port,
            env=body.env,
        )
    except DockerError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/containers/{uuid}/start", dependencies=[Depends(verify_node_key)])
async def start_container(uuid: str):
    try:
        return await get_docker_manager().start(uuid)
    except DockerError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/containers/{uuid}/stop", dependencies=[Depends(verify_node_key)])
async def stop_container(uuid: str, timeout: int = Query(30, ge=1, le=300)):
    try:
        return await get_docker_manager().stop(uuid, timeout=timeout)
    except DockerError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.delete("/containers/{uuid}", dependencies=[Depends(verify_node_key)])
async def delete_container(uuid: str):
    try:
        return await get_docker_manager().remove(uuid)
    except DockerError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/containers/{uuid}/status", dependencies=[Depends(verify_node_key)])
async def container_status(uuid: str):
    try:
        return await get_docker_manager().status(uuid)
    except DockerError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/containers/{uuid}/logs", dependencies=[Depends(verify_node_key)])
async def container_logs(uuid: str, tail: int = Query(200, ge=1, le=10_000)):
    try:
        text = await get_docker_manager().logs(uuid, tail=tail)
    except DockerError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"uuid": uuid, "logs": text}


@app.get("/containers/{uuid}/logs/stream", dependencies=[Depends(verify_node_key)])
async def container_log_stream(uuid: str):
    dm = get_docker_manager()

    async def _gen():
        async for line in dm.stream_logs(uuid):
            yield line + "\n"

    return StreamingResponse(_gen(), media_type="text/plain")
