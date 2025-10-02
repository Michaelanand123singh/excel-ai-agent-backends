# ============================================
# FILE 2: app/main.py (or wherever create_app is)
# ============================================
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time
import logging

from app.core.config import settings
from app.core.events import register_startup_event, register_shutdown_event
from app.api.v1.router import api_router_v1
from app.api.middleware.error_handler import http_error_handler

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
    # CORS Middleware (MUST be first, before other middlewares)
    # -----------------------------
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_origin_regex=settings.CORS_ALLOW_ORIGIN_REGEX,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Process-Time-ms"],
        max_age=600,
    )

    # -----------------------------
    # Logging Middleware
    # -----------------------------
    @application.middleware("http")
    async def logging_middleware(request: Request, call_next):
        # Log all requests
        origin = request.headers.get("origin", "no-origin")
        logger.info(f"📨 {request.method} {request.url.path} from {origin}")
        
        # Handle preflight OPTIONS requests immediately
        if request.method == "OPTIONS":
            logger.info(f"✅ Preflight OPTIONS handled for {request.url.path}")
            return Response(
                status_code=200,
                headers={
                    "Access-Control-Allow-Origin": origin if origin != "no-origin" else "*",
                    "Access-Control-Allow-Methods": "*",
                    "Access-Control-Allow-Headers": "*",
                    "Access-Control-Allow-Credentials": "true",
                }
            )
        
        start = time.perf_counter()
        try:
            response: Response = await call_next(request)
            duration_ms = (time.perf_counter() - start) * 1000
            response.headers["X-Process-Time-ms"] = f"{duration_ms:.2f}"
            logger.info(f"✅ {request.method} {request.url.path} - {response.status_code} ({duration_ms:.2f}ms)")
            return response
        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.error(f"❌ {request.method} {request.url.path} - Error: {str(e)} ({duration_ms:.2f}ms)")
            raise

    # -----------------------------
    # Security Headers Middleware
    # -----------------------------
    @application.middleware("http")
    async def security_headers_middleware(request: Request, call_next):
        # Skip security headers for preflight requests
        if request.method == "OPTIONS":
            return Response(status_code=200)
            
        response: Response = await call_next(request)
        
        # Only add security headers to HTML responses or when appropriate
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        
        # More permissive CSP for API
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self' data: blob:; "
            "connect-src 'self' https://excel-ai-agent-frontend-765930447632.asia-southeast1.run.app http://localhost:5173; "
            "img-src 'self' data: blob:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
        )
        return response

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
    # API router
    # -----------------------------
    application.include_router(api_router_v1, prefix="/api/v1")

    return application


app = create_app()