from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Integer

from .base import Base


class Query(Base):
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    question: Mapped[str] = mapped_column(String(2000))
    response: Mapped[str] = mapped_column(String(8000), default="")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)


