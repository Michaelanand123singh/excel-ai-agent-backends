from datetime import timedelta
from typing import Dict

from app.core.config import settings
from app.core.security import create_access_token


def issue_token(subject: str) -> str:
    minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
    secret = settings.JWT_SECRET or "dev-secret"
    alg = settings.JWT_ALGORITHM
    claims: Dict[str, str] = {"sub": subject}
    return create_access_token(claims, secret, alg, minutes)


