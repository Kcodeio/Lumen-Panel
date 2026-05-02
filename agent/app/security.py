"""Security for the node agent (node-key header check)."""
from __future__ import annotations

import hmac

from fastapi import Header, HTTPException

from app.config import settings


def verify_node_key(x_node_key: str | None = Header(default=None, alias="X-Node-Key")) -> bool:
    if not x_node_key or not hmac.compare_digest(x_node_key, settings.node_key):
        raise HTTPException(status_code=401, detail="Invalid node key")
    return True
