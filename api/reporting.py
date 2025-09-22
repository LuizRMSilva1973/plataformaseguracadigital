import os
from pathlib import Path
from sqlalchemy.orm import Session
from .models import Tenant, Report
from .notifications import send_email_with_attachment, send_email
from reports.generate_report import generate as gen_report


def generate_and_send_latest(db: Session, tenant_id: str) -> dict:
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        return {"ok": False, "error": "tenant not found"}
    if not tenant.alert_email:
        return {"ok": False, "error": "no alert email configured"}
    out_dir = "./data/reports"
    html_path = gen_report(tenant_id, out_dir=out_dir)
    # try to attach PDF if exists
    pdf_path = None
    p = Path(html_path)
    candidate = p.with_suffix(".pdf")
    if candidate.exists():
        pdf_path = str(candidate)
    subject = f"[DigitalSec] Relatório {tenant.name}"
    body = f"Olá, segue o relatório mais recente.\nAcesse também via painel."
    ok = False
    if pdf_path:
        ok = send_email_with_attachment(subject, body, tenant.alert_email, pdf_path, filename=Path(pdf_path).name)
    else:
        # Se não houver PDF, envia sem anexo e com link
        rel = html_path.split("data/")[-1]
        url = f"/static/{rel}"
        ok = send_email(subject, body + f"\nLink: {url}", tenant.alert_email)
    return {"ok": ok, "html_path": html_path, "pdf_path": pdf_path}

