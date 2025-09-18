from fastapi import APIRouter

from app.models.schemas.auth import Login, Token
from app.services.auth_service.jwt_handler import issue_token


router = APIRouter()


@router.post("/login", response_model=Token)
async def login(payload: Login) -> Token:
    # TODO: validate user against DB; for now issue token for any username
    token = issue_token(payload.username)
    return Token(access_token=token)


