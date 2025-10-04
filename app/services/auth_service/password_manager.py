"""
DEPRECATED: This module is deprecated. Use secure_password_manager.py instead.

This module is kept for backward compatibility only.
All new code should use the SecurePasswordManager from secure_password_manager.py.
"""

import warnings
from .secure_password_manager import (
    hash_password as _secure_hash_password,
    verify_password as _secure_verify_password,
    validate_password as _secure_validate_password,
    needs_update as _secure_needs_update,
    generate_secure_password as _secure_generate_password
)

# Issue deprecation warning
warnings.warn(
    "password_manager.py is deprecated. Use secure_password_manager.py instead.",
    DeprecationWarning,
    stacklevel=2
)


def hash_password(password: str) -> str:
    """
    Hash a password using the secure password manager.
    
    DEPRECATED: Use secure_password_manager.hash_password() instead.
    """
    return _secure_hash_password(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its hash.
    
    DEPRECATED: Use secure_password_manager.verify_password() instead.
    """
    return _secure_verify_password(plain_password, hashed_password)


def validate_password(password: str):
    """
    Validate password strength.
    
    DEPRECATED: Use secure_password_manager.validate_password() instead.
    """
    return _secure_validate_password(password)


def needs_update(hashed_password: str) -> bool:
    """
    Check if a password hash needs updating.
    
    DEPRECATED: Use secure_password_manager.needs_update() instead.
    """
    return _secure_needs_update(hashed_password)


def generate_secure_password(length: int = 16) -> str:
    """
    Generate a secure random password.
    
    DEPRECATED: Use secure_password_manager.generate_secure_password() instead.
    """
    return _secure_generate_password(length)


