from datetime import datetime, timedelta
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import select
from .models import Event, Incident


def classify_and_upsert_incidents(db: Session, tenant_id: str, window_minutes: int = 30):
    since = datetime.utcnow() - timedelta(minutes=window_minutes)
    # Load recent events (simple approach)
    rows = db.execute(
        select(Event).where(Event.tenant_id == tenant_id, Event.ts >= since)
    )
    brute = defaultdict(int)
    suspicious = []
    critical = []

    for (e,) in rows:
        if e.event_type in {"auth_failed", "ssh_auth_failed", "rdp_auth_failed"} and e.src_ip:
            key = (e.src_ip, e.username or "?")
            brute[key] += 1
        # suspicious execution
        rawmsg = str((e.raw_json or {}).get("message", ""))
        combined = f"{rawmsg} {e.app or ''} {e.event_type or ''}"
        if any(tok in combined.lower() for tok in ["powershell", "base64", "certutil", "wmic", "rundll32"]):
            suspicious.append(e)
        # critical change
        if e.event_type in {"sudoers_changed", "user_group_modified", "administrators_group_modified"}:
            critical.append(e)

    now = datetime.utcnow()
    new_critical_payloads = []
    # Upsert brute force incidents
    for (src_ip, username), count in brute.items():
        if count >= 5:  # threshold
            ctx = {"src_ip": src_ip, "username": username, "threshold": 5}
            inc = _upsert_incident(db, tenant_id, kind="brute_force", severity="high", context_key=("src_ip", src_ip), now=now, context=ctx)
            new_critical_payloads.append({"kind": "brute_force", "severity": "high", "context": ctx})

    # Upsert suspicious execution
    if suspicious:
        _upsert_incident(db, tenant_id, kind="suspicious_execution", severity="medium", context_key=("count", len(suspicious)), now=now, context={"count": len(suspicious)})

    # Upsert critical changes
    for e in critical:
        ctx = {"host": e.host, "event_type": e.event_type}
        _upsert_incident(db, tenant_id, kind="critical_change", severity="high", context_key=("event_type", e.event_type or ""), now=now, context=ctx)
        new_critical_payloads.append({"kind": "critical_change", "severity": "high", "context": ctx})

    db.commit()
    return new_critical_payloads


def _upsert_incident(db: Session, tenant_id: str, *, kind: str, severity: str, context_key: tuple, now: datetime, context: dict):
    inc = db.execute(
        select(Incident).where(Incident.tenant_id == tenant_id, Incident.kind == kind)
    ).scalars().first()
    if inc:
        inc.last_seen = now
        inc.count = (inc.count or 0) + 1
        inc.severity = severity
        inc.context_json = {**(inc.context_json or {}), **{context_key[0]: context_key[1]}, **context}
    else:
        inc = Incident(
            tenant_id=tenant_id,
            kind=kind,
            severity=severity,
            first_seen=now,
            last_seen=now,
            count=1,
            context_json={context_key[0]: context_key[1], **context},
            status="open",
        )
        db.add(inc)
    
