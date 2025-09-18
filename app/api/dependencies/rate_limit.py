from fastapi import Depends, HTTPException, status
from starlette.requests import Request
import time

from app.core.cache import get_redis_client


def rate_limit(max_requests: int, window_seconds: int):
    async def dependency(request: Request):
        client = get_redis_client()
        now = int(time.time())
        key = f"rl:{request.client.host}:{request.url.path}:{now // window_seconds}"
        count = client.incr(key)
        if count == 1:
            client.expire(key, window_seconds)
        if count > max_requests:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")
        return None
    return dependency


