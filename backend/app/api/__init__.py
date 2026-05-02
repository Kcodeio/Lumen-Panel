"""API routers."""
from fastapi import APIRouter

from app.api import auth, servers, nodes, ws

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(servers.router, prefix="/servers", tags=["servers"])
api_router.include_router(nodes.router, prefix="/nodes", tags=["nodes"])
api_router.include_router(ws.router, tags=["ws"])
