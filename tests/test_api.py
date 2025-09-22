import json
from fastapi.testclient import TestClient
from api.main import app
from api.database import init_db, SessionLocal
from api.models import Tenant


def setup_module():
    init_db()
    with SessionLocal() as db:
        if not db.query(Tenant).filter_by(id='t1').first():
            db.add(Tenant(id='t1', name='T1', plan='starter', ingest_token='tok-t1', status='active'))
            db.commit()


def auth():
    return {"Authorization": "Bearer tok-t1"}


def test_register_and_ingest_and_list():
    c = TestClient(app)
    # register
    r = c.post('/v1/agents/register', json={"agent_id":"AG-1","os":"linux","version":"0.1","host":"h1"}, headers=auth())
    assert r.status_code == 200
    # ingest
    batch = {
        "agent_id":"AG-1",
        "batch_id":"b1",
        "events":[{"ts":"2025-09-21T12:34:56Z","host":"h1","app":"linux-auth","event_type":"auth_failed","src_ip":"203.0.113.10","username":"root","severity":"high","raw":{"message":"Failed password"}}]
    }
    r = c.post('/v1/ingest', data=json.dumps(batch), headers={**auth(), "Content-Type":"application/json"})
    assert r.status_code == 200
    # incidents
    r = c.get('/v1/incidents', headers=auth())
    assert r.status_code == 200
    items = r.json().get('items', [])
    assert isinstance(items, list)

