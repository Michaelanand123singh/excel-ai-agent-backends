from pydantic import BaseModel


class FileRead(BaseModel):
    id: int
    filename: str
    size_bytes: int
    content_type: str
    status: str
    storage_path: str | None = None
    rows_count: int = 0
    elasticsearch_synced: bool = False
    elasticsearch_sync_error: str | None = None

    class Config:
        from_attributes = True


