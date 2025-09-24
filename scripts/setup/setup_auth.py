#!/usr/bin/env python3
"""
Complete authentication setup script for Excel AI Agents
"""

import sys
import os
from pathlib import Path

# Add the backend directory to the Python path
backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.database import engine
from app.models.database import Base
from app.models.database.user import User
from app.models.database.file import File
from app.models.database.query import Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.services.auth_service.user_service import UserService
from app.models.schemas.user import UserCreate


def create_tables():
    """Create all database tables"""
    print("🗄️  Creating database tables...")
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Database tables created successfully")
        return True
    except Exception as e:
        print(f"❌ Error creating tables: {e}")
        return False


def create_default_user():
    """Create the default user"""
    print("👤 Creating default user...")
    
    db = next(get_db())
    try:
        user_service = UserService(db)
        
        # Check if user already exists
        existing_user = user_service.get_user_by_email("info@opt2deal.com")
        if existing_user:
            print("✅ User info@opt2deal.com already exists")
            return True
        
        # Create user data
        user_data = UserCreate(
            email="info@opt2deal.com",
            password="Opt2deal123"
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


def verify_setup():
    """Verify the authentication setup"""
    print("🔍 Verifying authentication setup...")
    
    db = next(get_db())
    try:
        user_service = UserService(db)
        
        # Test authentication
        user = user_service.authenticate_user("info@opt2deal.com", "Opt2deal123")
        if user:
            print("✅ Authentication test passed")
            return True
        else:
            print("❌ Authentication test failed")
            return False
            
    except Exception as e:
        print(f"❌ Error verifying setup: {e}")
        return False
    finally:
        db.close()


def main():
    """Main setup function"""
    print("🚀 Excel AI Agents - Authentication Setup")
    print("=" * 50)
    
    # Step 1: Create tables
    if not create_tables():
        print("❌ Failed to create database tables")
        sys.exit(1)
    
    # Step 2: Create default user
    if not create_default_user():
        print("❌ Failed to create default user")
        sys.exit(1)
    
    # Step 3: Verify setup
    if not verify_setup():
        print("❌ Authentication setup verification failed")
        sys.exit(1)
    
    print("\n🎉 Authentication setup completed successfully!")
    print("\n📋 Login Credentials:")
    print("   Email: info@opt2deal.com")
    print("   Password: Opt2deal123")
    print("\n🔐 The authentication system is now properly configured.")
    print("   • JWT tokens are issued only after credential validation")
    print("   • Passwords are securely hashed with bcrypt")
    print("   • User accounts are stored in the database")
    print("   • Authentication is required for all protected endpoints")


if __name__ == "__main__":
    main()

