from passlib.context import CryptContext


# Use bcrypt_sha256 to safely support passwords > 72 bytes,
# while keeping bcrypt for backward compatibility during verification.
# New hashes will use bcrypt_sha256; verification will succeed for either.
pwd_context = CryptContext(
    schemes=["bcrypt_sha256", "bcrypt"],
    deprecated="auto",
)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


