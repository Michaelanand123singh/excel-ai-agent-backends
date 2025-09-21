from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.events import register_startup_event, register_shutdown_event
from app.api.v1.router import api_router_v1
from app.api.middleware.error_handler import http_error_handler


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # ------------------------------
    # CORS Middleware – must be FIRST
    # ------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ALLOW_ORIGINS,  # exact frontend URLs
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------
    # Security Headers Middleware
    # ------------------------------
    @app.middleware("http")
    async def security_headers_middleware(request: Request, call_next):
        # Allow OPTIONS preflight requests to succeed immediately
        if request.method == "OPTIONS":
            return Response(status_code=200)
        
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy",
            "geolocation=(), microphone=(), camera=()"
        )
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self' data: blob:; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline' 'unsafe-eval'"
        )
        return response

    # ------------------------------
    # Logging Middleware
    # ------------------------------
    @app.middleware("http")
    async def logging_middleware(request: Request, call_next):
        import time
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Process-Time-ms"] = f"{duration_ms:.2f}"
        return response

    # ------------------------------
    # Exception handler
    # ------------------------------
    app.add_exception_handler(Exception, http_error_handler)

    # ------------------------------
    # Startup / Shutdown events
    # ------------------------------
    register_startup_event(app)
    register_shutdown_event(app)

    # ------------------------------
    # API Routes
    # ------------------------------
    app.include_router(api_router_v1, prefix="/api/v1")

    return app


app = create_app()
