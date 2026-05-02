"""Docker container management for the node agent."""
from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path
from typing import Any, AsyncIterator

import docker
from docker.errors import APIError, ImageNotFound, NotFound
from docker.models.containers import Container

from app.config import settings

logger = logging.getLogger("lumen.agent.docker")


class DockerError(RuntimeError):
    pass


class DockerManager:
    """Wrap docker-py with the conventions used by Lumen."""

    def __init__(self) -> None:
        try:
            self.client = docker.from_env()
            # Force a connectivity check
            self.client.ping()
        except Exception as exc:  # pragma: no cover
            raise DockerError(f"Cannot reach Docker daemon: {exc}") from exc

    # ------------------------------------------------------------------ #
    # Naming
    # ------------------------------------------------------------------ #
    def _container_name(self, uuid: str) -> str:
        return f"{settings.container_prefix}{uuid}"

    def _server_dir(self, uuid: str) -> Path:
        d = Path(settings.data_dir) / "servers" / uuid
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ------------------------------------------------------------------ #
    # Lookup helpers
    # ------------------------------------------------------------------ #
    def _get_container(self, uuid: str) -> Container | None:
        try:
            return self.client.containers.get(self._container_name(uuid))
        except NotFound:
            return None
        except APIError as exc:
            raise DockerError(f"Docker API error: {exc}") from exc

    # ------------------------------------------------------------------ #
    # Image pulling (offloaded to a thread)
    # ------------------------------------------------------------------ #
    def _pull_image_blocking(self, image: str) -> None:
        try:
            self.client.images.get(image)
            return
        except ImageNotFound:
            pass
        except APIError as exc:
            raise DockerError(f"Image lookup failed: {exc}") from exc

        logger.info("Pulling image %s", image)
        try:
            self.client.images.pull(image)
        except APIError as exc:
            raise DockerError(f"Failed to pull image {image}: {exc}") from exc

    async def pull_image(self, image: str) -> None:
        await asyncio.to_thread(self._pull_image_blocking, image)

    # ------------------------------------------------------------------ #
    # Lifecycle operations
    # ------------------------------------------------------------------ #
    async def create(
        self,
        *,
        uuid: str,
        image: str,
        memory_mb: int,
        cpu_limit: float,
        host_port: int,
        env: dict[str, str],
    ) -> dict[str, Any]:
        existing = self._get_container(uuid)
        if existing is not None:
            return {
                "container_id": existing.id,
                "status": existing.status,
                "already_existed": True,
            }

        await self.pull_image(image)

        server_dir = self._server_dir(uuid)
        labels = {
            settings.container_label: "1",
            "com.lumen.uuid": uuid,
        }

        # Best-effort guess at common in-container ports for popular game images.
        # We fall back to publishing 25565 (Minecraft) which is most common for our
        # default use case; users can override via image-specific env vars.
        container_port = "25565/tcp"

        def _create() -> Container:
            try:
                return self.client.containers.create(
                    image=image,
                    name=self._container_name(uuid),
                    detach=True,
                    user="1000:1000",  # never run as root
                    mem_limit=f"{memory_mb}m",
                    memswap_limit=f"{memory_mb}m",
                    nano_cpus=int(cpu_limit * 1_000_000_000),
                    pids_limit=512,
                    cap_drop=["ALL"],
                    security_opt=["no-new-privileges:true"],
                    read_only=False,
                    network_mode="bridge",
                    ports={container_port: host_port},
                    environment=env,
                    volumes={
                        str(server_dir): {"bind": "/data", "mode": "rw"},
                    },
                    labels=labels,
                    restart_policy={"Name": "unless-stopped"},
                )
            except APIError as exc:
                raise DockerError(f"Failed to create container: {exc}") from exc

        container = await asyncio.to_thread(_create)
        return {"container_id": container.id, "status": "created"}

    async def start(self, uuid: str) -> dict[str, Any]:
        container = self._get_container(uuid)
        if container is None:
            raise DockerError("Container not found")

        def _start() -> str:
            try:
                container.start()
                container.reload()
                return container.id
            except APIError as exc:
                raise DockerError(f"Failed to start: {exc}") from exc

        cid = await asyncio.to_thread(_start)
        return {"container_id": cid, "status": "running"}

    async def stop(self, uuid: str, timeout: int = 30) -> dict[str, Any]:
        container = self._get_container(uuid)
        if container is None:
            return {"status": "stopped"}

        def _stop() -> None:
            try:
                container.stop(timeout=timeout)
            except APIError as exc:
                raise DockerError(f"Failed to stop: {exc}") from exc

        await asyncio.to_thread(_stop)
        return {"status": "stopped"}

    async def remove(self, uuid: str) -> dict[str, Any]:
        container = self._get_container(uuid)
        if container is not None:
            def _remove() -> None:
                try:
                    container.remove(force=True)
                except APIError as exc:
                    raise DockerError(f"Failed to remove: {exc}") from exc
            await asyncio.to_thread(_remove)

        # also remove the data directory (best-effort)
        server_dir = Path(settings.data_dir) / "servers" / uuid
        if server_dir.exists():
            await asyncio.to_thread(shutil.rmtree, server_dir, True)
        return {"status": "removed"}

    # ------------------------------------------------------------------ #
    # Status / stats
    # ------------------------------------------------------------------ #
    async def status(self, uuid: str) -> dict[str, Any]:
        container = self._get_container(uuid)
        if container is None:
            return {"status": "missing"}

        def _stats() -> dict[str, Any]:
            container.reload()
            base: dict[str, Any] = {
                "status": container.status,
                "container_id": container.id,
                "started_at": container.attrs.get("State", {}).get("StartedAt"),
            }
            if container.status != "running":
                return base
            try:
                s = container.stats(stream=False)
            except APIError:
                return base

            # CPU calculation
            cpu_delta = (
                s["cpu_stats"]["cpu_usage"]["total_usage"]
                - s["precpu_stats"]["cpu_usage"]["total_usage"]
            )
            sys_delta = (
                s["cpu_stats"].get("system_cpu_usage", 0)
                - s["precpu_stats"].get("system_cpu_usage", 0)
            )
            online_cpus = s["cpu_stats"].get("online_cpus") or len(
                s["cpu_stats"]["cpu_usage"].get("percpu_usage", []) or [1]
            )
            cpu_percent = 0.0
            if sys_delta > 0 and cpu_delta > 0:
                cpu_percent = (cpu_delta / sys_delta) * online_cpus * 100.0

            mem_usage = s["memory_stats"].get("usage", 0)
            mem_mb = mem_usage / 1024.0 / 1024.0

            base.update(
                {
                    "cpu_percent": round(cpu_percent, 2),
                    "memory_mb": round(mem_mb, 2),
                }
            )
            return base

        return await asyncio.to_thread(_stats)

    # ------------------------------------------------------------------ #
    # Logs
    # ------------------------------------------------------------------ #
    async def logs(self, uuid: str, tail: int = 200) -> str:
        container = self._get_container(uuid)
        if container is None:
            return ""

        def _logs() -> str:
            try:
                raw = container.logs(tail=tail, timestamps=False, stdout=True, stderr=True)
            except APIError as exc:
                raise DockerError(f"Failed to fetch logs: {exc}") from exc
            return raw.decode("utf-8", errors="replace")

        return await asyncio.to_thread(_logs)

    async def stream_logs(self, uuid: str) -> AsyncIterator[str]:
        """Yield log lines as they are produced."""
        container = self._get_container(uuid)
        if container is None:
            return

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=512)

        def _producer() -> None:
            try:
                stream = container.logs(stream=True, follow=True, tail=100)
                for chunk in stream:
                    asyncio.run_coroutine_threadsafe(queue.put(chunk), loop).result()
            except Exception as exc:  # noqa: BLE001
                logger.warning("log stream error: %s", exc)
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(None), loop)

        task = loop.run_in_executor(None, _producer)
        buffer = b""
        try:
            while True:
                chunk = await queue.get()
                if chunk is None:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    yield line.decode("utf-8", errors="replace")
            if buffer:
                yield buffer.decode("utf-8", errors="replace")
        finally:
            task.cancel()


# Module-level singleton
_dm: DockerManager | None = None


def get_docker_manager() -> DockerManager:
    global _dm
    if _dm is None:
        _dm = DockerManager()
    return _dm
