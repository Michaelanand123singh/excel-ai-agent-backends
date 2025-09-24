from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.models.schemas.auth import Login, Token
from app.models.schemas.user import UserCreate, UserRead
from app.services.auth_service.jwt_handler import issue_token
from app.services.auth_service.user_service import UserService
from app.api.dependencies.database import get_db


router = APIRouter()


@router.post("/login", response_model=Token)
async def login(payload: Login, db: Session = Depends(get_db)) -> Token:
    """Authenticate user and return JWT token"""
    user_service = UserService(db)
    
    # Authenticate user
    user = user_service.authenticate_user(payload.username, payload.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Issue token
    token = issue_token(user.email)
    return Token(access_token=token)


@router.post("/register", response_model=UserRead)
async def register(user_data: UserCreate, db: Session = Depends(get_db)) -> UserRead:
    """Register a new user"""
    user_service = UserService(db)
    
    try:
        user = user_service.create_user(user_data)
        return user
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


