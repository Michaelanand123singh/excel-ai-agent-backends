from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional


class Settings(BaseSettings):
    APP_NAME: str = "Excel AI Agent Backend"
    VERSION: str = "0.1.0"

    CORS_ALLOW_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost",
        "http://127.0.0.1",
    ]

    # Runtime
    ENV: str = "development"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Database / Supabase
    DATABASE_URL: Optional[str] = None  # e.g. postgresql+psycopg://user:pass@host:5432/db
    SUPABASE_URL: Optional[str] = None
    SUPABASE_ANON_KEY: Optional[str] = None
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = None
    SUPABASE_STORAGE_BUCKET: Optional[str] = None

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    JWT_SECRET: Optional[str] = None
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Vector/AI
    CHROMA_PERSIST_DIR: Optional[str] = ".chroma"
    GOOGLE_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-1.5-flash"

    # Ingestion tuning
    # Safe default to avoid exceeding database parameter limits on bulk inserts
    INGEST_BATCH_SIZE: int = 5000
    CHROMA_UPSERT_CHUNK: int = 5000
    DEFER_EMBEDDINGS: bool = False

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


