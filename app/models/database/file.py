from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Integer

from .base import Base


class File(Base):
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    filename: Mapped[str] = mapped_column(String(512), index=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    content_type: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(64), default="uploaded")
    storage_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    rows_count: Mapped[int] = mapped_column(Integer, default=0)
    elasticsearch_synced: Mapped[bool] = mapped_column(default=False)
    elasticsearch_sync_error: Mapped[str | None] = mapped_column(String(512), nullable=True)


