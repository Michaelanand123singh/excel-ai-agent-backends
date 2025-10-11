from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from typing import Generator

from app.core.config import settings


DATABASE_URL = settings.DATABASE_URL or "postgresql+psycopg://postgres:postgres@localhost:5432/excel_ai"

engine = create_engine(
    DATABASE_URL, 
    pool_pre_ping=True, 
    pool_size=1,  # Minimal pool size for Supabase
    max_overflow=2,  # Very limited overflow connections
    pool_timeout=30,  # Shorter timeout
    pool_recycle=1800,  # Recycle connections every 30 minutes
    connect_args={
        "connect_timeout": 30,  # Shorter connection timeout
    },
    echo=False  # Disable SQL logging for performance
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


