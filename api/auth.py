import os
from datetime import datetime, timedelta
import jwt
from passlib.hash import bcrypt
from fastapi import HTTPException
from sqlalchemy.orm import Session
from .models import User, Tenant


JWT_ALG = "HS256"


def create_user(db: Session, tenant_id: str, email: str, password: str, role: str = "org_admin") -> User:
    u = User(tenant_id=tenant_id, email=email, role=role, status="active", password_hash=bcrypt.hash(password))
    db.add(u)
    db.commit()
    return u


def verify_password(pw: str, hash_: str | None) -> bool:
    if not hash_:
        return False
    try:
        return bcrypt.verify(pw, hash_)
    except Exception:
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

