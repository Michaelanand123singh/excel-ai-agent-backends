from fastapi import APIRouter

from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.upload import router as upload_router
from app.api.v1.endpoints.query import router as query_router
from app.api.v1.endpoints.analytics import router as analytics_router
from app.api.v1.endpoints.websocket import router as websocket_router


api_router_v1 = APIRouter()
api_router_v1.include_router(health_router, prefix="/health", tags=["health"])
api_router_v1.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router_v1.include_router(upload_router, prefix="/upload", tags=["upload"])
api_router_v1.include_router(query_router, prefix="/query", tags=["query"])
api_router_v1.include_router(analytics_router, prefix="/analytics", tags=["analytics"])
# WebSocket router mounted at /api/v1/ws
api_router_v1.include_router(websocket_router, prefix="/ws", tags=["ws"])
