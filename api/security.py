import os
from fastapi import Header, HTTPException, Depends
from sqlalchemy.orm import Session
from .database import SessionLocal
from .models import Tenant
from .auth import decode_jwt


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_tenant(authorization: str | None = Header(None), db: Session = Depends(get_db)) -> Tenant:
    # Public mode: allow anonymous access under demo tenant
    public_mode = os.getenv("PUBLIC_ALLOW_ANON", "0").lower() in ("1", "true", "yes")
    if not authorization or not authorization.lower().startswith("bearer "):
        if public_mode:
            tenant = db.get(Tenant, "demo")
            if not tenant:
                tenant = Tenant(id="demo", name="Demo Org", plan="starter", ingest_token="demo-token", status="active")
                db.add(tenant)
                db.commit()
            if tenant and tenant.status == "active":
                return tenant
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    # Try JWT first (panel users)
    try:
        claims = decode_jwt(token)
        tid = claims.get("tenant_id")
        if tid:
            tenant = db.get(Tenant, tid)
            if tenant and tenant.status == "active":
                return tenant
    except Exception:
        pass
    # Fallback to ingest token (agents / legacy panel token)
    tenant = db.query(Tenant).filter(Tenant.ingest_token == token, Tenant.status == "active").first()
    if not tenant:
        raise HTTPException(status_code=401, detail="Invalid token")
    return tenant


def require_admin(x_api_secret: str | None = Header(None)):
    import os
    expected = os.getenv("API_SECRET")
    if not expected or x_api_secret != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True
