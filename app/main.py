from fastapi import FastAPI
import time
import logging

from app.core.config import settings
from app.core.events import register_startup_event, register_shutdown_event
from app.api.v1.router import api_router_v1
from app.api.middleware.error_handler import http_error_handler
from app.api.middleware.cors import CORSMiddleware, RobustCORSMiddleware
from app.api.middleware.logging import LoggingMiddleware
from app.api.middleware.security import SecurityHeadersMiddleware

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.APP_NAME,
        version=settings.VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Log CORS configuration on startup
    logger.info(f"🌐 CORS Origins: {settings.cors_origins_list}")
    logger.info(f"🌐 CORS Regex: {settings.CORS_ALLOW_ORIGIN_REGEX}")

    # -----------------------------
    # Middleware Configuration (Order matters!)
    # -----------------------------
    
    # 1. CORS Middleware (MUST be first)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_origin_regex=settings.CORS_ALLOW_ORIGIN_REGEX,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
        allow_headers=[
            "Accept",
            "Accept-Language",
            "Content-Language",
            "Content-Type",
            "Authorization",
            "X-Requested-With",
            "X-Request-Id",
            "x-request-id",
            "Origin",
            "Access-Control-Request-Method",
            "Access-Control-Request-Headers",
        ],
        expose_headers=["X-Process-Time-ms", "X-Request-Id", "x-request-id"],
        max_age=600,
    )

    # 2. Robust CORS Handler (handles database connection issues)
    application.add_middleware(RobustCORSMiddleware, enable_logging=True)

    # 3. Logging Middleware (logs requests and adds timing)
    application.add_middleware(LoggingMiddleware, log_level="INFO")

    # 4. Security Headers Middleware (adds security headers)
    application.add_middleware(SecurityHeadersMiddleware)

    # -----------------------------
    # Exception handler
    # -----------------------------
    application.add_exception_handler(Exception, http_error_handler)

    # -----------------------------
    # Startup / Shutdown events
    # -----------------------------
    register_startup_event(application)
    register_shutdown_event(application)

    # -----------------------------
    # Health check endpoint (before API router)
    # -----------------------------
    @application.get("/health")
    @application.get("/")
    async def health_check():
        return {
            "status": "healthy",
            "service": settings.APP_NAME,
            "version": settings.VERSION,
            "environment": settings.ENV
        }

    # -----------------------------
    # CORS test endpoint
    # -----------------------------
    @application.get("/cors-test")
    async def cors_test():
        return {
            "message": "CORS is working!",
            "cors_origins": settings.cors_origins_list,
            "cors_regex": settings.CORS_ALLOW_ORIGIN_REGEX,
            "middleware_stack": [
                "FastAPI CORSMiddleware",
                "RobustCORSMiddleware", 
                "LoggingMiddleware",
                "SecurityHeadersMiddleware"
            ]
        }

    # -----------------------------
    # CORS preflight test endpoint
    # -----------------------------
    @application.options("/cors-preflight-test")
    async def cors_preflight_test():
        """Test endpoint specifically for CORS preflight requests"""
        return {"message": "CORS preflight handled successfully"}

    # -----------------------------
    # Database health check
    # -----------------------------
    @application.get("/db-test")
    async def db_test():
        try:
            from app.core.database import engine
            with engine.connect() as conn:
                result = conn.execute("SELECT 1").fetchone()
                return {
                    "message": "Database connection successful!",
                    "test_query": result[0] if result else None
                }
        except Exception as e:
            logger.error(f"❌ Database connection failed: {str(e)}")
            return {
                "message": "Database connection failed!",
                "error": str(e)
            }

    # -----------------------------
    # Middleware test endpoint
    # -----------------------------
    @application.get("/middleware-test")
    async def middleware_test():
        return {
            "message": "Middleware is working!",
            "middleware_order": [
                "1. FastAPI CORSMiddleware",
                "2. RobustCORSMiddleware (database error handling)",
                "3. LoggingMiddleware (request logging & timing)", 
                "4. SecurityHeadersMiddleware (security headers)"
            ],
            "cors_configured": True,
            "logging_configured": True,
            "security_headers_configured": True,
            "robust_error_handling": True,
            "using_existing_classes": True
        }

    # -----------------------------
    # Comprehensive health check
    # -----------------------------
    @application.get("/health-comprehensive")
    async def comprehensive_health_check():
        health_status = {
            "service": settings.APP_NAME,
            "version": settings.VERSION,
            "environment": settings.ENV,
            "timestamp": time.time(),
            "components": {}
        }
        
        # Test CORS configuration
        try:
            health_status["components"]["cors"] = {
                "status": "healthy",
                "origins": settings.cors_origins_list,
                "regex": settings.CORS_ALLOW_ORIGIN_REGEX
            }
        except Exception as e:
            health_status["components"]["cors"] = {
                "status": "unhealthy",
                "error": str(e)
            }
        
        # Test database connection
        try:
            from app.core.database import engine
            with engine.connect() as conn:
                result = conn.execute("SELECT 1").fetchone()
                health_status["components"]["database"] = {
                    "status": "healthy",
                    "test_query": result[0] if result else None
                }
        except Exception as e:
            health_status["components"]["database"] = {
                "status": "unhealthy",
                "error": str(e)
            }
        
        # Test Redis connection
        try:
            from app.core.cache import get_redis_client
            get_redis_client().ping()
            health_status["components"]["redis"] = {
                "status": "healthy"
            }
        except Exception as e:
            health_status["components"]["redis"] = {
                "status": "unhealthy",
                "error": str(e)
            }
        
        # Overall status
        all_healthy = all(
            comp.get("status") == "healthy" 
            for comp in health_status["components"].values()
        )
        health_status["overall_status"] = "healthy" if all_healthy else "degraded"
        
        return health_status

    # -----------------------------
    # API router
    # -----------------------------
    application.include_router(api_router_v1, prefix="/api/v1")

    return application


app = create_app()