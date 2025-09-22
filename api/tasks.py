from api.database import SessionLocal
from api.main import _process_events


def process_events_job(tenant_id: str, agent_id: str, items: list[dict]):
    with SessionLocal() as db:
        _process_events(db, tenant_id, agent_id, items)

