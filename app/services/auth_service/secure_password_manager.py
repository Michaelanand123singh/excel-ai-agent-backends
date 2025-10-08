"""
Secure Password Manager - Unified, Robust Password Hashing System

This module provides a single, secure password hashing system that:
- Uses Argon2id (the most secure password hashing algorithm)
- Includes proper password validation
- Has consistent error handling
- No fallback systems - one robust method only
"""

import re
import secrets
import string
from typing import Tuple, Optional
from passlib.context import CryptContext
from passlib.exc import InvalidHashError, UnknownHashError


class PasswordValidationError(Exception):
    """Raised when password validation fails"""
    pass


class SecurePasswordManager:
    """
    Unified, secure password hashing system using Argon2id.
    
    Features:
    - Uses Argon2id (winner of Password Hashing Competition)
    - Memory-hard function that resists GPU/ASIC attacks
    - Configurable parameters for security vs performance
    - Proper password validation
    - Consistent error handling
    """
    
    def __init__(self):
        # Configure Argon2id with secure yet fast parameters
        # Tunable via environment variables for ops flexibility
        import os
        memory_cost = int(os.getenv("ARGON2_MEMORY_COST", "32768"))  # 32 MB (was 64 MB)
        time_cost = int(os.getenv("ARGON2_TIME_COST", "2"))          # 2 iterations (was 3)
        parallelism = int(os.getenv("ARGON2_PARALLELISM", "2"))       # 2 threads (was 4)

        self._context = CryptContext(
            schemes=["argon2"],
            default="argon2",
            argon2__memory_cost=memory_cost,
            argon2__time_cost=time_cost,
            argon2__parallelism=parallelism,
            argon2__hash_len=32,
            argon2__salt_len=16,
            deprecated="auto"
        )
        
        # Password validation rules
        self._min_length = 8
        self._max_length = 128
        self._require_uppercase = True
        self._require_lowercase = True
        self._require_digits = True
        self._require_special = True
        self._special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
    
    def validate_password(self, password: str) -> Tuple[bool, list]:
        """
        Validate password strength.
        
        Returns:
            Tuple[bool, list]: (is_valid, list_of_errors)
        """
        errors = []
        
        # Check length
        if len(password) < self._min_length:
            errors.append(f"Password must be at least {self._min_length} characters long")
        if len(password) > self._max_length:
            errors.append(f"Password must be no more than {self._max_length} characters long")
        
        # Check character requirements
        if self._require_uppercase and not re.search(r'[A-Z]', password):
            errors.append("Password must contain at least one uppercase letter")
        
        if self._require_lowercase and not re.search(r'[a-z]', password):
            errors.append("Password must contain at least one lowercase letter")
        
        if self._require_digits and not re.search(r'\d', password):
            errors.append("Password must contain at least one digit")
        
        if self._require_special and not re.search(f'[{re.escape(self._special_chars)}]', password):
            errors.append(f"Password must contain at least one special character: {self._special_chars}")
        
        # Check for common weak patterns
        if password.lower() in ['password', '123456', 'admin', 'user', 'test']:
            errors.append("Password is too common, please choose a stronger password")
        
        # Check for repeated characters
        if re.search(r'(.)\1{2,}', password):
            errors.append("Password contains too many repeated characters")
        
        return len(errors) == 0, errors
    
    def hash_password(self, password: str) -> str:
        """
        Hash a password using Argon2id.
        
        Args:
            password: Plain text password
            
        Returns:
            str: Hashed password
            
        Raises:
            PasswordValidationError: If password doesn't meet requirements
        """
        # Validate password
        is_valid, errors = self.validate_password(password)
        if not is_valid:
            raise PasswordValidationError(f"Password validation failed: {'; '.join(errors)}")
        
        # Hash the password
        try:
            return self._context.hash(password)
        except Exception as e:
            raise RuntimeError(f"Failed to hash password: {str(e)}")
    
    def verify_password(self, password: str, hashed_password: str) -> bool:
        """
        Verify a password against its hash.
        
        Args:
            password: Plain text password
            hashed_password: Stored password hash
            
        Returns:
            bool: True if password matches, False otherwise
        """
        try:
            return self._context.verify(password, hashed_password)
        except (InvalidHashError, UnknownHashError):
            # Hash format is invalid or unknown
            return False
        except Exception:
            # Any other error (shouldn't happen with Argon2)
            return False
    
    def needs_update(self, hashed_password: str) -> bool:
        """
        Check if a password hash needs to be updated.
        
        Args:
            hashed_password: Current password hash
            
        Returns:
            bool: True if hash should be updated
        """
        try:
            return self._context.needs_update(hashed_password)
        except Exception:
            # If we can't determine, assume it needs updating
            return True
    
    def generate_secure_password(self, length: int = 16) -> str:
        """
        Generate a secure random password.
        
        Args:
            length: Password length (default 16)
            
        Returns:
            str: Secure random password
        """
        if length < self._min_length:
            length = self._min_length
        
        # Character sets
        lowercase = string.ascii_lowercase
        uppercase = string.ascii_uppercase
        digits = string.digits
        special = self._special_chars
        
        # Ensure at least one character from each required set
        password = [
            secrets.choice(lowercase),
            secrets.choice(uppercase),
            secrets.choice(digits),
            secrets.choice(special)
        ]
        
        # Fill the rest with random characters
        all_chars = lowercase + uppercase + digits + special
        for _ in range(length - 4):
            password.append(secrets.choice(all_chars))
        
        # Shuffle the password
        secrets.SystemRandom().shuffle(password)
        
        return ''.join(password)


# Global instance
password_manager = SecurePasswordManager()


# Convenience functions for backward compatibility
def hash_password(password: str) -> str:
    """Hash a password using the secure password manager."""
    return password_manager.hash_password(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return password_manager.verify_password(plain_password, hashed_password)


def validate_password(password: str) -> Tuple[bool, list]:
    """Validate password strength."""
    return password_manager.validate_password(password)


def needs_update(hashed_password: str) -> bool:
    """Check if a password hash needs updating."""
    return password_manager.needs_update(hashed_password)


def generate_secure_password(length: int = 16) -> str:
    """Generate a secure random password."""
    return password_manager.generate_secure_password(length)
