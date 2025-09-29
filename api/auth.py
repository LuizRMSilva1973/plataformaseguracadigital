import os
import base64
import hashlib
from datetime import datetime, timedelta
import jwt
from fastapi import HTTPException
from sqlalchemy.orm import Session
from .models import User, Tenant


JWT_ALG = "HS256"
PBKDF2_ALG = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 260000


def _bcrypt_safe_password(pw: str) -> str:
    """Ensure password respects bcrypt's 72-byte limit.
    Truncates in bytes (UTF-8) if necessary to avoid ValueError during hashing.
    """
    try:
        b = pw.encode("utf-8")
    except Exception:
        # Fallback: keep original if encoding fails for some reason
        return pw
    if len(b) <= 72:
        return pw
    # Truncate to 72 bytes and decode (drop partial multibyte char if any)
    truncated = b[:72].decode("utf-8", "ignore")
    try:
        print("[auth] WARNING: Password provided exceeds 72 bytes; truncating for bcrypt compatibility.")
    except Exception:
        pass
    return truncated


def _hash_password_pbkdf2(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"{PBKDF2_ALG}${PBKDF2_ITERATIONS}${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(dk).decode()}"


def _verify_password_pbkdf2(password: str, encoded: str) -> bool:
    try:
        alg, iters, salt_b64, hash_b64 = encoded.split("$", 3)
        if alg != PBKDF2_ALG:
            return False
        iters_i = int(iters)
        salt = base64.urlsafe_b64decode(salt_b64.encode())
        expected = base64.urlsafe_b64decode(hash_b64.encode())
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iters_i)
        return hashlib.compare_digest(dk, expected)
    except Exception:
        return False


def create_user(db: Session, tenant_id: str, email: str, password: str, role: str = "org_admin") -> User:
    # Use PBKDF2-SHA256 (stdlib, no external deps). New users get this scheme.
    u = User(tenant_id=tenant_id, email=email, role=role, status="active", password_hash=_hash_password_pbkdf2(password))
    db.add(u)
    db.commit()
    return u


def verify_password(pw: str, hash_: str | None) -> bool:
    if not hash_:
        return False
    # Our default scheme
    if hash_.startswith(f"{PBKDF2_ALG}$"):
        return _verify_password_pbkdf2(pw, hash_)
    # Backward-compat: support bcrypt hashes if present
    if hash_.startswith("$2"):
        try:
            from passlib.hash import bcrypt as _bcrypt
            # Handle long secrets as some bcrypt backends error instead of truncating
            pw_safe = _bcrypt_safe_password(pw)
            return _bcrypt.verify(pw_safe, hash_)
        except Exception:
            return False
    return False


def create_jwt(tenant_id: str, user_id: int, role: str) -> str:
    secret = os.getenv("API_SECRET", "changeme")
    payload = {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=8)
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALG)


def decode_jwt(token: str) -> dict:
    secret = os.getenv("API_SECRET", "changeme")
    try:
        return jwt.decode(token, secret, algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="invalid token")
