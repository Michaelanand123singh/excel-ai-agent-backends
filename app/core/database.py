from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from typing import Generator

from app.core.config import settings


DATABASE_URL = settings.DATABASE_URL or "postgresql+psycopg://postgres:postgres@localhost:5432/excel_ai"

engine = create_engine(
    DATABASE_URL, 
    pool_pre_ping=True, 
    pool_size=20,  # Increased pool size
    max_overflow=30,  # More overflow connections
    pool_timeout=30,  # Connection timeout
    pool_recycle=3600,  # Recycle connections every hour
    echo=False  # Disable SQL logging for performance
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


