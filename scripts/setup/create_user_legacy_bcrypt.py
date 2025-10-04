#!/usr/bin/env python3
"""
DEPRECATED: This script is deprecated. Use migrate_to_secure_auth.py instead.

This script is kept for reference only.
All new user creation should use the secure authentication system.
"""

import sys
import warnings
from pathlib import Path

# Issue deprecation warning
warnings.warn(
    "create_user_legacy_bcrypt.py is deprecated. Use migrate_to_secure_auth.py instead.",
    DeprecationWarning,
    stacklevel=2
)

# Ensure backend package import
backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.services.auth_service.user_service import UserService
from app.models.schemas.user import UserCreate


def upsert_user(email: str, password: str) -> None:
    """Create or update user using secure authentication system"""
    from app.core.database import SessionLocal
    
    with SessionLocal() as db:
        user_service = UserService(db)
        
        # Check if user exists
        existing = user_service.get_user_by_email(email)
        if existing:
            # Update existing user with secure password
            try:
                user_service.update_user_password_by_email(email, password)
                print(f"✅ Updated existing user with secure auth: {email}")
            except Exception as e:
                print(f"❌ Error updating user: {e}")
            return
        
        # Create new user with secure authentication
        try:
            user_data = UserCreate(email=email, password=password)
            user = user_service.create_user(user_data)
            print(f"✅ Created secure user: {user.email} (ID: {user.id})")
        except Exception as e:
            print(f"❌ Error creating user: {e}")


def main() -> None:
    email = sys.argv[1] if len(sys.argv) > 1 else "official@opt2deal.com"
    password = sys.argv[2] if len(sys.argv) > 2 else "Opt2deal123"
    print("🔐 Creating user with secure authentication system...")
    print("⚠️  Note: This script now uses the secure authentication system.")
    upsert_user(email, password)


if __name__ == "__main__":
    main()



