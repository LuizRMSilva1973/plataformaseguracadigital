import json
from fastapi.testclient import TestClient
from api.main import app
from api.database import init_db, SessionLocal
from api.models import Tenant


def setup_module():
    init_db()
    with SessionLocal() as db:
        if not db.query(Tenant).filter_by(id='t3').first():
            db.add(Tenant(id='t3', name='T3', plan='starter', ingest_token='tok-t3', status='active'))
            db.commit()


def auth():
    return {"Authorization": "Bearer tok-t3"}


def test_bruteforce_incident_and_checklist_and_blockip():
    c = TestClient(app)
    # register agent
    r = c.post('/v1/agents/register', json={"agent_id":"AG-3","os":"linux","version":"0.1","host":"h3"}, headers=auth())
    assert r.status_code == 200
    # ingest 6 failed auths from same IP to trigger rule
    events = []
    for i in range(6):
        events.append({"ts":"2025-09-21T12:34:56Z","host":"h3","app":"linux-auth","event_type":"auth_failed","src_ip":"203.0.113.99","username":"root","severity":"high","raw":{"message":"Failed password"}})
    batch = {"agent_id":"AG-3","batch_id":"b3","events":events}
    r = c.post('/v1/ingest', data=json.dumps(batch), headers={**auth(), "Content-Type":"application/json"})
    assert r.status_code == 200
    # incidents should include brute_force
    inc = c.get('/v1/incidents', headers=auth()).json()["items"]
    assert any(x["kind"] == "brute_force" for x in inc)
    # checklist should suggest blocking the IP
    cl = c.get('/v1/checklist', headers=auth()).json()["items"]
    assert any("Bloquear IP" in x["title"] for x in cl)
    # block ip action
    r = c.post('/v1/actions/block_ip', json={"ip":"203.0.113.99", "provider":"local"}, headers=auth())
    assert r.status_code == 200
    assert r.json().get("ok") is True

