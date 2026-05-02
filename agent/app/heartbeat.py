"""Background heartbeat loop that pings the panel."""
from __future__ import annotations

import asyncio
import logging
import socket
from datetime import datetime, timezone

import httpx
import psutil

from app.config import settings
from app import __version__

logger = logging.getLogger("lumen.agent.heartbeat")


async def register_with_panel() -> None:
    body = {
        "hostname": socket.gethostname(),
        "agent_version": __version__,
        "docker_version": None,
    }
    try:
        from app.docker_manager import get_docker_manager
        body["docker_version"] = get_docker_manager().client.version().get("Version")
    except Exception:
        pass

    headers = {"X-Node-Key": settings.node_key, "Content-Type": "application/json"}
    url = f"{settings.panel_url.rstrip('/')}/api/v1/nodes/register"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(url, json=body, headers=headers)
            logger.info("Registered with panel at %s", settings.panel_url)
    except Exception as exc:
        logger.warning("Failed to register with panel: %s", exc)


async def heartbeat_loop(interval_seconds: int = 30) -> None:
    """Send periodic heartbeats to the panel forever."""
    headers = {"X-Node-Key": settings.node_key, "Content-Type": "application/json"}
    url = f"{settings.panel_url.rstrip('/')}/api/v1/nodes/heartbeat"

    while True:
        try:
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory().percent
            running = 0
            try:
                from app.docker_manager import get_docker_manager
                running = len(
                    get_docker_manager().client.containers.list(
                        filters={"label": settings.container_label}
                    )
                )
            except Exception:
                pass

            body = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "cpu_percent": cpu,
                "memory_percent": mem,
                "running_containers": running,
            }
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(url, json=body, headers=headers)
        except Exception as exc:
            logger.debug("Heartbeat failed: %s", exc)
        await asyncio.sleep(interval_seconds)
