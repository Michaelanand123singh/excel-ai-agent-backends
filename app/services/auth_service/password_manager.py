from passlib.context import CryptContext
import hashlib


# Primary: bcrypt for hashing, with SHA-256 pre-hashing to avoid 72-byte limit
_bcrypt_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Fallback reader for any existing $bcrypt-sha256$ hashes that might exist
_bcrypt_sha256_ctx = CryptContext(schemes=["bcrypt_sha256"], deprecated="auto")


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    # Always pre-hash with SHA-256, then bcrypt the hex digest
    prehashed = _sha256_hex(password)
    return _bcrypt_ctx.hash(prehashed)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    # 1) If stored hash is bcrypt_sha256 format, let passlib verify it directly
    if hashed_password.startswith("$bcrypt-sha256$"):
        try:
            return _bcrypt_sha256_ctx.verify(plain_password, hashed_password)
        except Exception:
            return False

    # 2) Try our new scheme: bcrypt of SHA-256 hex
    try:
        prehashed = _sha256_hex(plain_password)
        if _bcrypt_ctx.verify(prehashed, hashed_password):
            return True
    except Exception:
        pass

    # 3) Legacy fallback: try verifying raw password against bcrypt (only if <=72 bytes)
    try:
        if len(plain_password.encode("utf-8")) <= 72:
            return _bcrypt_ctx.verify(plain_password, hashed_password)
    except Exception:
        pass

    return False


