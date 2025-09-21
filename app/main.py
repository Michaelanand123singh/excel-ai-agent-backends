from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
import time

from app.core.config import settings
from app.core.events import register_startup_event, register_shutdown_event
from app.api.v1.router import api_router_v1
from app.api.middleware.error_handler import http_error_handler


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.APP_NAME,
        version=settings.VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # -----------------------------
    # CORS Middleware (keep first)
    # -----------------------------
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ALLOW_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -----------------------------
    # Logging Middleware
    # -----------------------------
    @application.middleware("http")
    async def logging_middleware(request: Request, call_next):
        start = time.perf_counter()
        response: Response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Process-Time-ms"] = f"{duration_ms:.2f}"
        return response

    # -----------------------------
    # Security Headers Middleware
    # -----------------------------
    @application.middleware("http")
    async def security_headers_middleware(request: Request, call_next):
        response: Response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self' data: blob:; "
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
    # API router
    # -----------------------------
    application.include_router(api_router_v1, prefix="/api/v1")

    return application


app = create_app()
