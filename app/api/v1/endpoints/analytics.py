from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.dependencies.database import get_db
from app.models.database.query import Query as QueryModel


router = APIRouter()


@router.get("/summary")
async def analytics_summary(db: Session = Depends(get_db)) -> dict:
    total = db.query(func.count(QueryModel.id)).scalar() or 0
    avg_latency = db.query(func.coalesce(func.avg(QueryModel.latency_ms), 0)).scalar() or 0
    return {"total_queries": int(total), "avg_latency_ms": int(avg_latency)}


