import os
from datetime import datetime, timedelta
from typing import List

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from .database import init_db, SessionLocal
from .models import Tenant, Agent, Event, Incident, IngestBatch, Subscription, Asset, Notification
from .schemas import IngestBatchIn, AgentRegisterIn, ScoreOut, EventIn
from .security import require_tenant, get_db, require_admin
from .auth import create_user, verify_password, create_jwt
from .actions import block_ip
from .reporting import generate_and_send_latest
from .ratelimit import check_rate
from .reputation import get_ip_reputation
from .notifications import send_email

app = FastAPI(title="DigitalSec Platform API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


@app.on_event("startup")
def on_startup():
    init_db()
    # Seed a demo tenant if none
    with SessionLocal() as db:
        if not db.query(Tenant).count():
            demo = Tenant(id="demo", name="Demo Org", plan="starter", ingest_token="demo-token", status="active")
            db.add(demo)
            db.commit()
        # Seed default user
        admin_email = os.getenv("ADMIN_EMAIL")
        admin_password = os.getenv("ADMIN_PASSWORD")
        from .models import User
        # If ADMIN_* provided, ensure that user exists; otherwise, if there are no users at all, create a sensible default for local dev
        if admin_email and admin_password:
            user = db.query(User).filter_by(email=admin_email).first()
            if not user:
                create_user(db, tenant_id="demo", email=admin_email, password=admin_password, role="org_admin")
        else:
            # Bootstrap a default admin only if there are no users yet
            if db.query(User).count() == 0:
                create_user(db, tenant_id="demo", email="admin@local", password="admin123", role="org_admin")
    # Prepare static dir for reports
    os.makedirs("data/reports", exist_ok=True)

app.mount("/static", StaticFiles(directory="data"), name="static")

# Job agendado simples (gera relatório diário) — habilite com ENABLE_SCHEDULER=1
if os.getenv("ENABLE_SCHEDULER", "0").lower() in ("1", "true", "yes"):
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        scheduler = BackgroundScheduler()
        def daily_reports():
            with SessionLocal() as db:
                rows = db.execute(select(Tenant)).scalars().all()
                from reports.generate_report import generate as gen
                auto_email = os.getenv("REPORT_AUTO_EMAIL", "1").lower() in ("1","true","yes")
                for t in rows:
                    try:
                        # sempre gera e registra
                        gen(t.id, out_dir="./data/reports")
                        # envia se configurado
                        if auto_email and t.alert_email:
                            try:
                                generate_and_send_latest(db, t.id)
                            except Exception:
                                pass
                    except Exception:
                        pass
        interval_minutes = int(os.getenv("SCHEDULER_INTERVAL_MINUTES", "1440"))
        scheduler.add_job(daily_reports, 'interval', minutes=interval_minutes, id='daily_reports', replace_existing=True)
        scheduler.start()
    except Exception:
        scheduler = None


@app.post("/v1/agents/register")
def register_agent(payload: AgentRegisterIn, tenant: Tenant = Depends(require_tenant), db: Session = Depends(get_db)):
    agent = db.get(Agent, payload.agent_id)
    now = datetime.utcnow()
    if agent:
        agent.os = payload.os or agent.os
        agent.version = payload.version or agent.version
        agent.last_seen_at = now
    else:
        agent = Agent(id=payload.agent_id, tenant_id=tenant.id, os=payload.os, version=payload.version, last_seen_at=now)
        db.add(agent)
    # upsert asset by host if provided
    host = getattr(payload, 'host', None)
    if host:
        asset = db.execute(select(Asset).where(Asset.tenant_id == tenant.id, Asset.host == host)).scalars().first()
        if asset:
            asset.os = payload.os or asset.os
            asset.last_seen_at = now
            asset.agent_id = agent.id
        else:
            asset = Asset(tenant_id=tenant.id, host=host, os=payload.os, last_seen_at=now, agent_id=agent.id)
            db.add(asset)
    db.commit()
    # Simple config answer
    return {
        "agent_id": agent.id,
        "upload_interval_sec": 60,
        "feature_flags": {"ip_reputation": tenant.plan != "starter"}
    }


@app.get("/v1/config")
def get_config(tenant: Tenant = Depends(require_tenant)):
    return {
        "upload_interval_sec": 60,
        "blocklists": [],
        "feature_flags": {"ip_reputation": tenant.plan != "starter"}
    }


def _process_events(db: Session, tenant_id: str, agent_id: str, items: List[dict]):
    # Persist events, enrich IP reputation e gerar incidentes
    from .rules import classify_and_upsert_incidents
    ips = set()
    for e in items:
        ts = datetime.fromisoformat(e.get("ts").replace("Z", "+00:00")) if e.get("ts") else datetime.utcnow()
        ev = Event(
            tenant_id=tenant_id,
            agent_id=agent_id,
            ts=ts,
            host=e.get("host"),
            app=e.get("app"),
            event_type=e.get("event_type"),
            src_ip=e.get("src_ip"),
            dst_ip=e.get("dst_ip"),
            username=e.get("username"),
            severity=e.get("severity"),
            raw_json=e.get("raw")
        )
        db.add(ev)
        if e.get("src_ip"):
            ips.add(e.get("src_ip"))
    db.commit()
    # Enriquecimento de reputação (cache)
    for ip in ips:
        try:
            get_ip_reputation(db, ip)
        except Exception:
            pass
    new_crit = classify_and_upsert_incidents(db, tenant_id)
    # Notificações por e-mail se configurado
    tenant = db.get(Tenant, tenant_id)
    for inc in new_crit:
        notif = Notification(tenant_id=tenant_id, kind="incident", severity=inc.get("severity","high"), channel="email", payload_json=inc, status="pending")
        db.add(notif)
    db.commit()
    if tenant and tenant.alert_email:
        for inc in new_crit:
            subj = f"[DigitalSec] Incidente {inc.get('kind')} - {inc.get('severity')}"
            body = f"Incidente: {inc.get('kind')}\nSeveridade: {inc.get('severity')}\nContexto: {inc.get('context')}"
            ok = send_email(subj, body, tenant.alert_email)
            status = "sent" if ok else "failed"
            notif = Notification(tenant_id=tenant_id, kind="incident", severity=inc.get("severity","high"), channel="email", payload_json=inc, status=status)
            db.add(notif)
        db.commit()


@app.post("/v1/ingest")
async def ingest(request: Request, background: BackgroundTasks, tenant: Tenant = Depends(require_tenant), db: Session = Depends(get_db)):
    # Per-tenant rate limit
    check_rate(f"ingest:{tenant.id}")
    # Handle optional gzip Content-Encoding
    raw = await request.body()
    if request.headers.get("content-encoding", "").lower() == "gzip":
        import gzip
        raw = gzip.decompress(raw)
    import json
    data = json.loads(raw.decode("utf-8"))
    try:
        payload = IngestBatchIn(**data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid payload: {e}")
    # Idempotency check
    exists = db.query(IngestBatch).filter_by(tenant_id=tenant.id, agent_id=payload.agent_id, batch_id=payload.batch_id).first()
    if exists:
        return {"status": "duplicate", "accepted": 0}
    rec = IngestBatch(tenant_id=tenant.id, agent_id=payload.agent_id, batch_id=payload.batch_id)
    db.add(rec)
    db.commit()
    # Processamento assíncrono: usa RQ se REDIS_URL estiver configurado; senão BackgroundTasks
    try:
        import os
        if os.getenv("REDIS_URL"):
            from rq import Queue
            import redis
            r = redis.Redis.from_url(os.getenv("REDIS_URL"))
            q = Queue("ingest", connection=r)
            q.enqueue("api.tasks.process_events_job", tenant.id, payload.agent_id, [e.dict(by_alias=True) | {"ts": e.ts} for e in payload.events])
        else:
            background.add_task(_process_events, db, tenant.id, payload.agent_id, [e.dict(by_alias=True) | {"ts": e.ts} for e in payload.events])
    except Exception:
        background.add_task(_process_events, db, tenant.id, payload.agent_id, [e.dict(by_alias=True) | {"ts": e.ts} for e in payload.events])
    return {"status": "accepted", "accepted": len(payload.events)}


@app.get("/v1/incidents")
def list_incidents(tenant: Tenant = Depends(require_tenant), db: Session = Depends(get_db)):
    from fastapi import Query
    # Read filters via request query manual; list recentes, filtros em /v1/incidents/search.
    # We'll just list recent 200 for now, advanced filters exposed in separate endpoint.
    q = db.execute(select(Incident).where(Incident.tenant_id == tenant.id).order_by(Incident.last_seen.desc()).limit(200))
    items = []
    for (inc,) in q:
        items.append({
            "id": inc.id,
            "kind": inc.kind,
            "severity": inc.severity,
            "first_seen": inc.first_seen.isoformat(),
            "last_seen": inc.last_seen.isoformat(),
            "count": inc.count,
            "context": inc.context_json,
            "status": inc.status,
        })
    return {"items": items}


@app.post("/auth/login")
async def login(payload: dict, db: Session = Depends(get_db)):
    email = payload.get("email")
    password = payload.get("password")
    if not email or not password:
        raise HTTPException(status_code=400, detail="missing email/password")
    from .models import User
    user = db.query(User).filter_by(email=email, status="active").first()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")
    token = create_jwt(user.tenant_id, user.id, user.role)
    return {"token": token, "tenant_id": user.tenant_id, "role": user.role}


@app.get("/v1/incidents/search")
def search_incidents(
    request: Request,
    tenant: Tenant = Depends(require_tenant),
    db: Session = Depends(get_db)
):
    params = request.query_params
    severity = params.get("severity")
    status = params.get("status")
    host = params.get("host")
    since = params.get("since")
    until = params.get("until")
    limit = int(params.get("limit", 200))
    q = select(Incident).where(Incident.tenant_id == tenant.id)
    if severity:
        q = q.where(Incident.severity == severity)
    if status:
        q = q.where(Incident.status == status)
    from datetime import datetime
    def parse_dt(s):
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None
    if since:
        dt = parse_dt(since)
        if dt:
            q = q.where(Incident.last_seen >= dt)
    if until:
        dt = parse_dt(until)
        if dt:
            q = q.where(Incident.last_seen <= dt)
    q = q.order_by(Incident.last_seen.desc()).limit(min(1000, max(1, limit)))
    items = []
    for (inc,) in db.execute(q):
        if host and (not inc.context_json or inc.context_json.get("host") != host):
            continue
        items.append({
            "id": inc.id,
            "kind": inc.kind,
            "severity": inc.severity,
            "first_seen": inc.first_seen.isoformat(),
            "last_seen": inc.last_seen.isoformat(),
            "count": inc.count,
            "context": inc.context_json,
            "status": inc.status,
        })
    return {"items": items}


@app.get("/v1/score", response_model=ScoreOut)
def get_score(tenant: Tenant = Depends(require_tenant), db: Session = Depends(get_db)):
    window = int(os.getenv("SCORE_DEFAULT_WINDOW_DAYS", "7"))
    since = datetime.utcnow() - timedelta(days=window)
    sev_weight = {"low": 1, "medium": 3, "high": 7, "critical": 12}
    q = db.execute(select(Incident.severity, func.sum(Incident.count)).where(Incident.tenant_id == tenant.id, Incident.last_seen >= since).group_by(Incident.severity))
    total = 0
    for severity, cnt in q:
        total += sev_weight.get(severity or "low", 1) * int(cnt or 0)
    # Very simple score: 100 - scaled incident weight.
    score = max(0, 100 - min(100, total))
    return ScoreOut(score=score, window_days=window)


# Simple billing webhooks (stubs)
@app.post("/billing/webhook/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    # Simplificado: espera JSON {tenant_id, event}
    # event in {"invoice.paid", "payment_failed", "subscription.deleted"}
    body = await request.json()
    tenant_id = body.get("tenant_id")
    event = body.get("event")
    if tenant_id and event:
        tenant = db.get(Tenant, tenant_id)
        if tenant:
            sub = db.query(Subscription).filter_by(tenant_id=tenant.id, provider="stripe").first()
            if not sub:
                sub = Subscription(tenant_id=tenant.id, provider="stripe", status="inactive")
                db.add(sub)
            if event == "invoice.paid":
                tenant.status = "active"
                sub.status = "active"
            elif event in ("payment_failed", "subscription.deleted"):
                tenant.status = "past_due" if event == "payment_failed" else "canceled"
                sub.status = "past_due" if event == "payment_failed" else "canceled"
            db.commit()
    return {"received": True}


@app.post("/billing/webhook/pagarme")
def pagarme_webhook():
    return {"received": True}


@app.get("/v1/reports/latest")
def latest_report(tenant: Tenant = Depends(require_tenant)):
    # Gera on-demand e retorna URL estática
    from reports.generate_report import generate as gen  # type: ignore
    path = gen(tenant.id, out_dir="./data/reports")
    rel = path.split("data/")[-1]
    return {"url_html": f"/static/{rel}"}


@app.get("/v1/assets")
def list_assets(tenant: Tenant = Depends(require_tenant), db: Session = Depends(get_db)):
    q = db.execute(select(Asset).where(Asset.tenant_id == tenant.id).order_by(Asset.last_seen_at.desc().nullslast()))
    items = []
    for (a,) in q:
        items.append({
            "host": a.host,
            "os": a.os,
            "last_seen_at": a.last_seen_at.isoformat() if a.last_seen_at else None,
            "agent_id": a.agent_id
        })
    return {"items": items}


@app.post("/v1/incidents/{incident_id}/ack")
def ack_incident(incident_id: int, tenant: Tenant = Depends(require_tenant), db: Session = Depends(get_db)):
    inc = db.get(Incident, incident_id)
    if not inc or inc.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="not found")
    inc.status = "ack"
    db.commit()
    return {"ok": True}


@app.post("/v1/actions/block_ip")
def api_block_ip(payload: dict, tenant: Tenant = Depends(require_tenant), db: Session = Depends(get_db)):
    ip = payload.get("ip")
    provider = payload.get("provider", "local")
    if not ip:
        raise HTTPException(status_code=400, detail="missing ip")
    ok = block_ip(db, tenant, ip, provider)
    return {"ok": ok}


@app.get("/v1/reports")
def list_reports(tenant: Tenant = Depends(require_tenant), db: Session = Depends(get_db)):
    from .models import Report
    rows = db.execute(select(Report).where(Report.tenant_id == tenant.id).order_by(Report.period_end.desc()).limit(20))
    items = []
    for (r,) in rows:
        items.append({
            "id": r.id,
            "period_start": r.period_start.isoformat(),
            "period_end": r.period_end.isoformat(),
            "url_html": r.url_pdf,
            "score": r.score,
        })
    return {"items": items}


@app.post("/v1/reports/send_latest")
def send_latest_report(tenant: Tenant = Depends(require_tenant), db: Session = Depends(get_db)):
    res = generate_and_send_latest(db, tenant.id)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "send failed"))
    rel = res["html_path"].split("data/")[-1]
    return {"ok": True, "url_html": f"/static/{rel}", "pdf": bool(res.get("pdf_path"))}


def _ensure_checklist(db: Session, tenant_id: str):
    from .models import ChecklistItem
    # Deriva recomendações simples a partir dos incidentes abertos
    rows = db.execute(select(Incident).where(Incident.tenant_id == tenant_id, Incident.status == "open")).scalars().all()
    for inc in rows:
        if inc.kind == "brute_force":
            key = f"block-ip-{(inc.context_json or {}).get('src_ip','')}"
            title = f"Bloquear IP { (inc.context_json or {}).get('src_ip','desconhecido') } no firewall"
        elif inc.kind == "suspicious_execution":
            key = "audit-powershell"
            title = "Auditar uso de PowerShell e desabilitar execução remota se possível"
        elif inc.kind == "critical_change":
            key = f"review-priv-groups-{(inc.context_json or {}).get('host','')}"
            title = f"Revisar grupos de privilégio no host { (inc.context_json or {}).get('host','') }"
        else:
            key = f"review-incident-{inc.id}"
            title = f"Revisar incidente {inc.kind}"
        exists = db.execute(select(ChecklistItem).where(ChecklistItem.tenant_id == tenant_id, ChecklistItem.key == key)).scalars().first()
        if not exists:
            db.add(ChecklistItem(tenant_id=tenant_id, key=key, title=title, context_json=inc.context_json or {}))
    db.commit()


@app.get("/v1/checklist")
def get_checklist(tenant: Tenant = Depends(require_tenant), db: Session = Depends(get_db)):
    from .models import ChecklistItem
    _ensure_checklist(db, tenant.id)
    rows = db.execute(select(ChecklistItem).where(ChecklistItem.tenant_id == tenant.id).order_by(ChecklistItem.created_at.desc())).scalars().all()
    return {"items": [{"key": r.key, "title": r.title, "done": r.done, "context": r.context_json} for r in rows]}


@app.post("/v1/checklist/{key}/done")
def mark_checklist_done(key: str, tenant: Tenant = Depends(require_tenant), db: Session = Depends(get_db)):
    from .models import ChecklistItem
    item = db.execute(select(ChecklistItem).where(ChecklistItem.tenant_id == tenant.id, ChecklistItem.key == key)).scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="not found")
    item.done = True
    db.commit()
    return {"ok": True}


# Admin endpoints (requer X-API-Secret)
import secrets


@app.post("/admin/tenants")
async def create_tenant(payload: dict, _: bool = Depends(require_admin), db: Session = Depends(get_db)):
    tid = payload.get("id") or secrets.token_urlsafe(6)
    name = payload.get("name") or tid
    plan = payload.get("plan", "starter")
    token = secrets.token_urlsafe(24)
    alert_email = payload.get("alert_email")
    t = Tenant(id=tid, name=name, plan=plan, ingest_token=token, status="active", alert_email=alert_email)
    db.add(t)
    db.commit()
    return {"id": tid, "ingest_token": token, "plan": plan, "alert_email": alert_email}


@app.post("/admin/tenants/{tenant_id}/rotate-token")
async def rotate_token(tenant_id: str, _: bool = Depends(require_admin), db: Session = Depends(get_db)):
    t = db.get(Tenant, tenant_id)
    if not t:
        raise HTTPException(status_code=404, detail="tenant not found")
    token = secrets.token_urlsafe(24)
    t.ingest_token = token
    db.commit()
    return {"id": tenant_id, "ingest_token": token}


@app.get("/admin/tenants")
async def list_tenants(_: bool = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.execute(select(Tenant)).scalars().all()
    return [{"id": r.id, "name": r.name, "plan": r.plan, "status": r.status, "alert_email": r.alert_email} for r in rows]


@app.post("/admin/tenants/{tenant_id}/alert-email")
async def set_alert_email(tenant_id: str, payload: dict, _: bool = Depends(require_admin), db: Session = Depends(get_db)):
    t = db.get(Tenant, tenant_id)
    if not t:
        raise HTTPException(status_code=404, detail="tenant not found")
    t.alert_email = payload.get("alert_email")
    db.commit()
    return {"ok": True}


@app.post("/admin/users")
async def admin_create_user(payload: dict, _: bool = Depends(require_admin), db: Session = Depends(get_db)):
    # Create a user under a tenant (admin only via X-API-Secret)
    tenant_id = payload.get("tenant_id") or "demo"
    email = payload.get("email")
    password = payload.get("password")
    role = payload.get("role", "viewer")
    if not email or not password:
        raise HTTPException(status_code=400, detail="email and password are required")
    t = db.get(Tenant, tenant_id)
    if not t:
        raise HTTPException(status_code=404, detail="tenant not found")
    from .models import User
    exists = db.query(User).filter_by(tenant_id=tenant_id, email=email).first()
    if exists:
        raise HTTPException(status_code=409, detail="user already exists")
    u = create_user(db, tenant_id=tenant_id, email=email, password=password, role=role)
    return {"id": u.id, "tenant_id": u.tenant_id, "email": u.email, "role": u.role, "status": u.status}


# Minimal rules module inline import fallback
try:
    from . import rules  # noqa: F401
except Exception:
    pass
