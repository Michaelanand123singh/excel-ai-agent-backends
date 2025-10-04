#!/usr/bin/env python3
"""
Migration script to clean up old users and create new users with secure authentication.

This script:
1. Deletes all existing users (cleaning up incompatible hashes)
2. Creates a new user with the secure password system
3. Tests the new authentication system
4. Provides working credentials
"""

import sys
from pathlib import Path

# Ensure backend package import
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import delete
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.database.user import User
from app.services.auth_service.user_service import UserService
from app.models.schemas.user import UserCreate
from app.services.auth_service.secure_password_manager import generate_secure_password


def clean_database():
    """Delete all existing users from the database"""
    print("🧹 Cleaning database - removing all existing users...")
    
    with SessionLocal() as db:
        try:
            # Delete all users
            result = db.execute(delete(User))
            db.commit()
            print(f"✅ Deleted {result.rowcount} users from database")
            return True
        except Exception as e:
            print(f"❌ Error cleaning database: {e}")
            return False


def create_secure_user(email: str, password: str):
    """Create a new user with secure authentication"""
    print(f"🔐 Creating secure user: {email}")
    
    with SessionLocal() as db:
        try:
            user_service = UserService(db)
            
            # Create user data
            user_data = UserCreate(
                email=email,
                password=password
            )
            
            # Create user (this will validate password strength)
            user = user_service.create_user(user_data)
            print(f"✅ Created secure user: {user.email} (ID: {user.id})")
            return True
            
        except Exception as e:
            print(f"❌ Error creating user: {e}")
            return False


def test_authentication(email: str, password: str):
    """Test the new authentication system"""
    print(f"🧪 Testing authentication for: {email}")
    
    with SessionLocal() as db:
        try:
            user_service = UserService(db)
            
            # Test authentication
            auth_user = user_service.authenticate_user(email, password)
            if auth_user:
                print("✅ Authentication successful!")
                print(f"   User ID: {auth_user.id}")
                print(f"   Email: {auth_user.email}")
                print(f"   Active: {auth_user.is_active}")
                return True
            else:
                print("❌ Authentication failed")
                return False
                
        except Exception as e:
            print(f"❌ Authentication error: {e}")
            return False


def main():
    """Main migration function"""
    print("🚀 Excel AI Agents - Secure Authentication Migration")
    print("=" * 60)
    
    # Configuration
    email = "official@opt2deal.com"
    password = "Opt2deal123!"  # Added special character for security
    
    print(f"📧 Email: {email}")
    print(f"🔑 Password: {password}")
    print()
    
    # Step 1: Clean database
    if not clean_database():
        print("❌ Failed to clean database")
        sys.exit(1)
    
    # Step 2: Create secure user
    if not create_secure_user(email, password):
        print("❌ Failed to create secure user")
        sys.exit(1)
    
    # Step 3: Test authentication
    if not test_authentication(email, password):
        print("❌ Authentication test failed")
        sys.exit(1)
    
    # Success!
    print("\n🎉 MIGRATION COMPLETED SUCCESSFULLY!")
    print("=" * 60)
    print("📋 Your new secure credentials:")
    print(f"   Email: {email}")
    print(f"   Password: {password}")
    print()
    print("🔐 Security features enabled:")
    print("   ✅ Argon2id password hashing (most secure algorithm)")
    print("   ✅ Password strength validation")
    print("   ✅ Memory-hard hashing (resists GPU/ASIC attacks)")
    print("   ✅ Configurable security parameters")
    print("   ✅ No fallback systems (single robust method)")
    print()
    print("🌐 You can now use these credentials to log in to your application!")


if __name__ == "__main__":
    main()
