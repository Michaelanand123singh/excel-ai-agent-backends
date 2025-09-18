from pydantic import BaseModel


class QueryCreate(BaseModel):
    question: str


class QueryRead(BaseModel):
    id: int
    user_id: int
    question: str
    response: str
    latency_ms: int

    class Config:
        from_attributes = True


