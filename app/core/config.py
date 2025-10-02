from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import List, Optional, Union
import os
import json


class Settings(BaseSettings):
    APP_NAME: str = "Excel AI Agent Backend"
    VERSION: str = "0.1.0"

    # CORS - Handle both JSON array and comma-separated string
    CORS_ALLOW_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost,http://127.0.0.1,https://excel-ai-agent-frontend-765930447632.asia-southeast1.run.app"
    # Optional regex to match dynamic frontend URLs (e.g., Cloud Run revisions)
    CORS_ALLOW_ORIGIN_REGEX: Optional[str] = os.getenv(
        "CORS_ALLOW_ORIGIN_REGEX",
        r"^https:\/\/excel-ai-agent-frontend-[0-9]+\.asia-southeast1\.run\.app$",
    )
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Convert CORS_ALLOW_ORIGINS string to list"""
        if isinstance(self.CORS_ALLOW_ORIGINS, str):
            return [origin.strip() for origin in self.CORS_ALLOW_ORIGINS.split(",")]
        return self.CORS_ALLOW_ORIGINS

    # Runtime
    ENV: str = os.getenv("ENV", "development")
    DEBUG: bool = os.getenv("DEBUG", "True").lower() == "true"
    HOST: str = "0.0.0.0"
    PORT: int = int(os.getenv("PORT", "8080"))  # Cloud Run provides PORT=8080

    # Database / Supabase
    DATABASE_URL: Optional[str] = None  # e.g. postgresql+psycopg://user:pass@host:5432/db
    SUPABASE_URL: Optional[str] = None
    SUPABASE_ANON_KEY: Optional[str] = None
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = None
    SUPABASE_STORAGE_BUCKET: Optional[str] = None

    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # JWT
    JWT_SECRET: Optional[str] = os.getenv("JWT_SECRET", None)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Vector/AI
    CHROMA_PERSIST_DIR: Optional[str] = ".chroma"
    GOOGLE_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-1.5-flash"

    # Elasticsearch
    ES_HOST: Optional[str] = os.getenv("ES_HOST")  # e.g. https://<cloud-endpoint>:443
    ES_USERNAME: Optional[str] = os.getenv("ES_USERNAME")
    ES_PASSWORD: Optional[str] = os.getenv("ES_PASSWORD")
    ES_API_KEY: Optional[str] = os.getenv("ES_API_KEY")  # Base64 API key (id:api_key)
    ES_INDEX_PREFIX: str = os.getenv("ES_INDEX_PREFIX", "parts_search")
    ES_TIMEOUT_MS: int = int(os.getenv("ES_TIMEOUT_MS", "5000"))

    # Ingestion tuning
    INGEST_BATCH_SIZE: int = 5000
    CHROMA_UPSERT_CHUNK: int = 5000
    DEFER_EMBEDDINGS: bool = False

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
