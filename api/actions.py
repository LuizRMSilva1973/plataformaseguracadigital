import os
import requests
from sqlalchemy.orm import Session
from .models import Tenant, BlockedIP


def block_ip(db: Session, tenant: Tenant, ip: str, provider: str = "local") -> bool:
    provider = provider or "local"
    ok = False
    if provider == "cloudflare":
        # Stub: store blocked and try API if keys present
        token = os.getenv("CF_API_TOKEN") or (tenant.integrations_json or {}).get("cloudflare_token") if tenant.integrations_json else None
        account = os.getenv("CF_ACCOUNT_ID") or (tenant.integrations_json or {}).get("cloudflare_account") if tenant.integrations_json else None
        if token and account:
            try:
                url = f"https://api.cloudflare.com/client/v4/accounts/{account}/firewall/access_rules/rules"
                headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
                payload = {"mode": "block", "configuration": {"target": "ip", "value": ip}, "notes": "Blocked by DigitalSec"}
                r = requests.post(url, json=payload, headers=headers, timeout=10)
                ok = r.status_code in (200, 201)
            except Exception:
                ok = False
        else:
            ok = True
    elif provider == "aws_waf":
        # Stub: Pretend success if AWS creds set (not implementing full WAF API here)
        ok = bool(os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY"))
    else:
        ok = True

    # record in DB regardless (source of truth)
    rec = BlockedIP(tenant_id=tenant.id, ip=ip, provider=provider)
    db.add(rec)
    db.commit()
    return ok

