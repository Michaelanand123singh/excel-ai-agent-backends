from fastapi import APIRouter
from sqlalchemy import text

from app.core.database import engine
from app.core.cache import get_redis_client


router = APIRouter()


@router.get("/live")
async def liveness_probe() -> dict:
    return {"status": "ok"}


@router.get("/ready")
async def readiness_probe() -> dict:
    status = {"db": False, "cache": False}
    # DB check
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        status["db"] = True
    except Exception:
        status["db"] = False
    # Redis check
    try:
        client = get_redis_client()
        client.ping()
        status["cache"] = True
    except Exception:
        status["cache"] = False
    overall = status["db"] and status["cache"]
    return {"status": "ready" if overall else "degraded", **status}

