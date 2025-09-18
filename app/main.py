from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.events import register_startup_event, register_shutdown_event
from app.api.v1.router import api_router_v1
from app.api.middleware.logging import LoggingMiddleware
from app.api.middleware.security import SecurityHeadersMiddleware
from app.api.middleware.error_handler import http_error_handler


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.APP_NAME,
        version=settings.VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ALLOW_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.add_middleware(LoggingMiddleware)
    application.add_middleware(SecurityHeadersMiddleware)

    application.add_exception_handler(Exception, http_error_handler)

    register_startup_event(application)
    register_shutdown_event(application)

    application.include_router(api_router_v1, prefix="/api/v1")

    return application


app = create_app()
