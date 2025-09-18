from fastapi import FastAPI
from app.core.logging import configure_logging
import logging

from sqlalchemy import text
from app.core.database import engine
from app.core.cache import get_redis_client
from app.core.config import settings
from app.services.supabase_client import get_supabase
from app.services.vector_store.chroma_client import get_client as get_chroma
from app.models.database import Base


def register_startup_event(app: FastAPI) -> None:
    @app.on_event("startup")
    async def on_startup() -> None:
        configure_logging()
        log = logging.getLogger("startup")
        log.info("Starting %s v%s", settings.APP_NAME, settings.VERSION)

        # DB
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            # Auto-create tables if missing
            Base.metadata.create_all(bind=engine)
            log.info("DB: connected")
        except Exception as e:
            log.error("DB: connection failed: %s", e)

        # Redis
        try:
            get_redis_client().ping()
            log.info("Redis: connected")
        except Exception as e:
            log.error("Redis: connection failed: %s", e)

        # Supabase
        try:
            if settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY:
                get_supabase()
                log.info("Supabase: client initialized")
            else:
                log.info("Supabase: skipped (missing config)")
        except Exception as e:
            log.error("Supabase: init failed: %s", e)

        # ChromaDB
        try:
            get_chroma()
            log.info("ChromaDB: client ready (path=%s)", settings.CHROMA_PERSIST_DIR)
        except Exception as e:
            log.error("ChromaDB: init failed: %s", e)
        return None


def register_shutdown_event(app: FastAPI) -> None:
    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        # Cleanup resources
        return None


