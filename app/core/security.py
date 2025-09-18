from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import jwt


def create_access_token(data: Dict[str, Any], secret: str, algorithm: str, expires_minutes: int) -> str:
    to_encode = data.copy()
    expire = datetime.now(tz=timezone.utc) + timedelta(minutes=expires_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, secret, algorithm=algorithm)


