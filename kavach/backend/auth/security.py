"""security.py — Direct bcrypt password hashing and JWT token handling for KAVACH."""

from datetime import datetime, timedelta, timezone
import os
from typing import Any, Dict, Optional

import bcrypt
from jose import JWTError, jwt

# Secret key & token parameters
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "kavach_sovereign_auth_secret_key_2026_mrpl")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_DAYS = 7


def hash_password(password: str) -> str:
    """Hashes a plain text password using native bcrypt."""
    pwd_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against its bcrypt hash."""
    try:
        pwd_bytes = plain_password.encode("utf-8")[:72]
        hash_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(pwd_bytes, hash_bytes)
    except Exception:
        return False


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Creates an encoded JWT access token with an expiration timestamp."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(days=JWT_EXPIRATION_DAYS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decodes and verifies a JWT access token, returning the payload dict or None."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError:
        return None
