"""HTTP client used by the panel to call the node agent."""
from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings


class AgentClientError(RuntimeError):
    """Raised when the agent returns an error or is unreachable."""


class AgentClient:
    """Thin wrapper over httpx for talking to the lumen-agent."""

    def __init__(self, base_url: str | None = None, node_key: str | None = None) -> None:
        self.base_url = (base_url or settings.agent_url).rstrip("/")
        self.node_key = node_key or settings.node_key
        self._timeout = httpx.Timeout(15.0, connect=5.0)

    def _headers(self) -> dict[str, str]:
        return {"X-Node-Key": self.node_key, "Content-Type": "application/json"}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.request(
                    method, url, json=json, params=params, headers=self._headers()
                )
        except httpx.HTTPError as exc:
            raise AgentClientError(f"Agent unreachable: {exc}") from exc

        if resp.status_code >= 400:
            raise AgentClientError(
                f"Agent error {resp.status_code}: {resp.text[:300]}"
            )
        if resp.headers.get("content-type", "").startswith("application/json"):
            return resp.json()
        return resp.text

    # ------------------------------------------------------------------
    # High-level methods
    # ------------------------------------------------------------------
    async def health(self) -> dict[str, Any]:
        return await self._request("GET", "/health")

    async def create_container(
        self,
        *,
        uuid: str,
        image: str,
        memory_mb: int,
        cpu_limit: float,
        host_port: int,
        env: dict[str, str],
    ) -> dict[str, Any]:
        body = {
            "uuid": uuid,
            "image": image,
            "memory_mb": memory_mb,
            "cpu_limit": cpu_limit,
            "host_port": host_port,
            "env": env,
        }
        return await self._request("POST", "/containers", json=body)

    async def start_container(self, uuid: str) -> dict[str, Any]:
        return await self._request("POST", f"/containers/{uuid}/start")

    async def stop_container(self, uuid: str, *, timeout: int = 30) -> dict[str, Any]:
        return await self._request(
            "POST", f"/containers/{uuid}/stop", params={"timeout": timeout}
        )

    async def remove_container(self, uuid: str) -> dict[str, Any]:
        return await self._request("DELETE", f"/containers/{uuid}")

    async def container_status(self, uuid: str) -> dict[str, Any]:
        return await self._request("GET", f"/containers/{uuid}/status")

    async def container_logs(self, uuid: str, *, tail: int = 200) -> str:
        result = await self._request("GET", f"/containers/{uuid}/logs", params={"tail": tail})
        if isinstance(result, dict):
            return result.get("logs", "")
        return result or ""
