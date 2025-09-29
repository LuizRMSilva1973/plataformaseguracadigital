from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from .models import Tenant, Subscription
from .security import require_tenant, get_db

def require_active_subscription(tenant: Tenant = Depends(require_tenant), db: Session = Depends(get_db)):
    subscription = db.query(Subscription).filter(Subscription.tenant_id == tenant.id).first()

    if not subscription or subscription.status != "active":
        raise HTTPException(status_code=402, detail="Active subscription required")

    return tenant
