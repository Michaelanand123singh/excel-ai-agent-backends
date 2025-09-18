from __future__ import annotations

from typing import List

from app.core.cache import get_redis_client


def _key(user_id: int, file_id: int) -> str:
    return f"ctx:{user_id}:{file_id}"


def add_message(user_id: int, file_id: int, role: str, content: str, max_history: int = 10) -> None:
    client = get_redis_client()
    client.lpush(_key(user_id, file_id), f"{role}:{content}")
    client.ltrim(_key(user_id, file_id), 0, max_history - 1)


def get_history(user_id: int, file_id: int, limit: int = 10) -> List[str]:
    client = get_redis_client()
    return client.lrange(_key(user_id, file_id), 0, limit - 1) or []



