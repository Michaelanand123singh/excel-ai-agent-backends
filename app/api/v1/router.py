from fastapi import APIRouter

from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.upload import router as upload_router
from app.api.v1.endpoints.query import router as query_router
from app.api.v1.endpoints.analytics import router as analytics_router
from app.api.v1.endpoints.websocket import router as websocket_router
from app.api.v1.endpoints.bulk_search import router as bulk_search_router
from app.api.v1.endpoints.query_optimized import router as query_optimized_router
from app.api.v1.endpoints.query_elasticsearch import router as query_elasticsearch_router


api_router_v1 = APIRouter()
api_router_v1.include_router(health_router, prefix="/health", tags=["health"])
api_router_v1.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router_v1.include_router(upload_router, prefix="/upload", tags=["upload"])
api_router_v1.include_router(query_router, prefix="/query", tags=["query"])
api_router_v1.include_router(query_optimized_router, prefix="/query-optimized", tags=["query-optimized"])
api_router_v1.include_router(query_elasticsearch_router, prefix="/query-elasticsearch", tags=["query-elasticsearch"])
api_router_v1.include_router(analytics_router, prefix="/analytics", tags=["analytics"])
api_router_v1.include_router(bulk_search_router, prefix="/bulk-search", tags=["bulk-search"])
# WebSocket router mounted at /api/v1/ws
api_router_v1.include_router(websocket_router, prefix="/ws", tags=["ws"])
