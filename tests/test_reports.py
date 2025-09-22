import os
from fastapi.testclient import TestClient
from api.main import app
from api.database import init_db, SessionLocal
from api.models import Tenant


def setup_module():
    init_db()
    with SessionLocal() as db:
        if not db.query(Tenant).filter_by(id='t2').first():
            db.add(Tenant(id='t2', name='T2', plan='starter', ingest_token='tok-t2', status='active'))
            db.commit()


def auth():
    return {"Authorization": "Bearer tok-t2"}


def test_latest_report_endpoint_no_pdf():
    os.environ['REPORT_PDF'] = 'false'
    c = TestClient(app)
    r = c.get('/v1/reports/latest', headers=auth())
    assert r.status_code == 200
    data = r.json()
    assert 'url_html' in data

