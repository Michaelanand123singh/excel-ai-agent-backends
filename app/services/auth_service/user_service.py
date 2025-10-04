from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import Optional

from app.models.database.user import User
from app.models.schemas.user import UserCreate, UserRead
from app.services.auth_service.secure_password_manager import hash_password, verify_password, validate_password, PasswordValidationError


class UserService:
    def __init__(self, db: Session):
        self.db = db

    def create_user(self, user_data: UserCreate) -> UserRead:
        """Create a new user with hashed password"""
        # Check if user already exists
        existing_user = self.get_user_by_email(user_data.email)
        if existing_user:
            raise ValueError("User with this email already exists")
        
        # Validate password strength
        is_valid, errors = validate_password(user_data.password)
        if not is_valid:
            raise ValueError(f"Password validation failed: {'; '.join(errors)}")
        
        # Hash the password
        hashed_password = hash_password(user_data.password)
        
        # Create user
        db_user = User(
            email=user_data.email,
            hashed_password=hashed_password,
            is_active=True
        )
        
        self.db.add(db_user)
        self.db.commit()
        self.db.refresh(db_user)
        
        return UserRead(
            id=db_user.id,
            email=db_user.email,
            is_active=db_user.is_active
        )

    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email"""
        stmt = select(User).where(User.email == email)
        result = self.db.execute(stmt)
        return result.scalar_one_or_none()

    def authenticate_user(self, email: str, password: str) -> Optional[User]:
        """Authenticate user with email and password"""
        user = self.get_user_by_email(email)
        if not user:
            return None
        
        if not user.is_active:
            return None
            
        if not verify_password(password, user.hashed_password):
            return None
            
        return user

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Get user by ID"""
        stmt = select(User).where(User.id == user_id)
        result = self.db.execute(stmt)
        return result.scalar_one_or_none()

    def update_user_password(self, user_id: int, new_password: str) -> bool:
        """Update user password"""
        user = self.get_user_by_id(user_id)
        if not user:
            return False
        
        # Validate new password
        is_valid, errors = validate_password(new_password)
        if not is_valid:
            raise ValueError(f"Password validation failed: {'; '.join(errors)}")
        
        user.hashed_password = hash_password(new_password)
        self.db.commit()
        return True
    
    def update_user_password_by_email(self, email: str, new_password: str) -> bool:
        """Update user password by email"""
        user = self.get_user_by_email(email)
        if not user:
            return False
        
        # Validate new password
        is_valid, errors = validate_password(new_password)
        if not is_valid:
            raise ValueError(f"Password validation failed: {'; '.join(errors)}")
        
        user.hashed_password = hash_password(new_password)
        self.db.commit()
        return True
    
    def migrate_user_password(self, user_id: int, old_password: str) -> bool:
        """
        Migrate a user's password from old hash format to new secure format.
        This is useful for updating users with legacy password hashes.
        """
        user = self.get_user_by_id(user_id)
        if not user:
            return False
        
        # Verify the old password first
        if not verify_password(old_password, user.hashed_password):
            return False
        
        # Update to new secure hash
        user.hashed_password = hash_password(old_password)
        self.db.commit()
        return True

    def deactivate_user(self, user_id: int) -> bool:
        """Deactivate user account"""
        user = self.get_user_by_id(user_id)
        if not user:
            return False
        
        user.is_active = False
        self.db.commit()
        return True

