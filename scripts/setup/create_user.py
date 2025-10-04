#!/usr/bin/env python3
"""
Script to create the default user for the Excel AI Agents system
"""

import sys
import os
from pathlib import Path
import argparse

# Add the backend directory to the Python path
backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.database.user import User
from app.services.auth_service.password_manager import hash_password
from app.services.auth_service.user_service import UserService
from app.models.schemas.user import UserCreate


def create_user(email: str, password: str) -> bool:
    """Create a user with the provided credentials"""
    print(f"🔐 Creating user {email}...")

    db = next(get_db())

    try:
        user_service = UserService(db)

        # Check if user already exists
        existing_user = user_service.get_user_by_email(email)
        if existing_user:
            print(f"✅ User {email} already exists")
            return True

        # Create user data
        user_data = UserCreate(
            email=email,
            password=password,
        )

        # Create user
        user = user_service.create_user(user_data)
        print(f"✅ User created successfully: {user.email} (ID: {user.id})")
        return True

    except Exception as e:
        print(f"❌ Error creating user: {e}")
        return False
    finally:
        db.close()


def main():
    """Main function"""
    print("🚀 Excel AI Agents - User Creation Script")
    print("=" * 50)

    parser = argparse.ArgumentParser(description="Create a user with email and password")
    parser.add_argument("--email", dest="email", default=os.getenv("CREATE_USER_EMAIL", "info@opt2deal.com"))
    parser.add_argument("--password", dest="password", default=os.getenv("CREATE_USER_PASSWORD", "Opt2deal123"))
    args = parser.parse_args()

    success = create_user(args.email, args.password)

    if success:
        print("\n🎉 User creation completed successfully!")
        print("\n📋 Login Credentials:")
        print(f"   Email: {args.email}")
        print(f"   Password: {args.password}")
        print("\n🔐 You can now use these credentials to log in to the system.")
    else:
        print("\n❌ User creation failed. Please check the error messages above.")
        sys.exit(1)


if __name__ == "__main__":
    main()

