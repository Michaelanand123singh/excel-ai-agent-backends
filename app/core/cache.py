import redis
from app.core.config import settings


def get_redis_client(url: str | None = None) -> redis.Redis:
    return redis.from_url(url or settings.REDIS_URL, decode_responses=True)


