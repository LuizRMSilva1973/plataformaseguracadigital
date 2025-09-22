from datetime import datetime, timedelta
from pathlib import Path
from jinja2 import Template
import os
from sqlalchemy.orm import Session
from sqlalchemy import select

from api.database import SessionLocal
from api.models import Tenant, Incident, Report


TEMPLATE = Template(
    """
<!doctype html>
<html><head><meta charset="utf-8"><title>Relatório de Segurança</title>
<style>body{font-family:Arial,Helvetica,sans-serif;margin:24px}h1{margin:0}small{color:#666}.card{border:1px solid #ddd;border-radius:8px;padding:12px 16px;margin:8px 0}</style>
</head><body>
  <h1>Relatório de Segurança — {{ tenant.name }}</h1>
  <small>Período: {{ start }} a {{ end }}</small>
  <div class="card"><b>Nota de Segurança:</b> {{ score }}/100</div>
  <div class="card"><b>Top Incidentes</b>
    <ul>
    {% for i in incidents %}
      <li>{{ i.kind }} — {{ i.severity }} — {{ i.count }} ocorrências ({{ i.last_seen }})</li>
    {% endfor %}
    </ul>
  </div>
</body></html>
    """
)


def compute_score(db: Session, tenant_id: str, start: datetime, end: datetime) -> int:
    from api.main import get_score  # reuse weights logic if needed
    sev_weight = {"low": 1, "medium": 3, "high": 7, "critical": 12}
    q = db.execute(select(Incident.severity, Incident.count).where(Incident.tenant_id == tenant_id, Incident.last_seen >= start, Incident.last_seen <= end))
    total = 0
    for severity, cnt in q:
        total += sev_weight.get(severity or "low", 1) * int(cnt or 0)
    return max(0, 100 - min(100, total))


def generate(tenant_id: str, out_dir: str = "./data/reports") -> str:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    start = datetime.utcnow() - timedelta(days=7)
    end = datetime.utcnow()
    with SessionLocal() as db:
        tenant = db.get(Tenant, tenant_id)
        if not tenant:
            raise RuntimeError("tenant not found")
        rows = db.execute(select(Incident).where(Incident.tenant_id == tenant_id).order_by(Incident.count.desc()).limit(10))
        incidents = []
        for (i,) in rows:
            incidents.append({"kind": i.kind, "severity": i.severity, "count": i.count, "last_seen": i.last_seen.isoformat()})
        score = compute_score(db, tenant_id, start, end)
        html = TEMPLATE.render(tenant=tenant, start=start.date(), end=end.date(), incidents=incidents, score=score)
        out = Path(out_dir) / f"report_{tenant_id}_{end.date()}.html"
        out.write_text(html, encoding="utf-8")
        pdf_url = None
        if os.getenv("REPORT_PDF", "false").lower() in ("1","true","yes"):
            try:
                from weasyprint import HTML  # type: ignore
                pdf_path = Path(out_dir) / f"report_{tenant_id}_{end.date()}.pdf"
                HTML(string=html).write_pdf(str(pdf_path))
                pdf_url = "/static/" + str(pdf_path).split("data/")[-1]
            except Exception:
                pdf_url = None
        # save report record
        rel_path = str(out).split("data/")[-1]
        rep = Report(tenant_id=tenant_id, period_start=start, period_end=end, url_pdf=pdf_url or f"/static/{rel_path}", score=score, summary_json={"top_incidents": incidents})
        db.add(rep)
        db.commit()
        return str(out)


if __name__ == "__main__":
    import sys
    tid = sys.argv[1] if len(sys.argv) > 1 else "demo"
    path = generate(tid)
    print("report:", path)
