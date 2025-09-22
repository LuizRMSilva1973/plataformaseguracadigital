import os
import smtplib
from email.message import EmailMessage
from typing import Optional


def send_email(subject: str, body: str, to_email: str) -> bool:
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASS")
    from_email = os.getenv("SMTP_FROM", user or "noreply@example.com")
    if not host or not to_email:
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email
    msg.set_content(body)
    try:
        with smtplib.SMTP(host, port, timeout=10) as s:
            s.starttls()
            if user:
                s.login(user, password or "")
            s.send_message(msg)
        return True
    except Exception:
        return False


def send_whatsapp(message: str, to_number: str) -> bool:
    # Stub: Use Meta WA Cloud API if WHATSAPP_TOKEN and WHATSAPP_PHONE_ID set
    import os, requests
    token = os.getenv("WHATSAPP_TOKEN")
    phone_id = os.getenv("WHATSAPP_PHONE_ID")
    if not token or not phone_id:
        return False
    try:
        url = f"https://graph.facebook.com/v19.0/{phone_id}/messages"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {"messaging_product": "whatsapp", "to": to_number, "type": "text", "text": {"body": message}}
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        return r.status_code in (200,201)
    except Exception:
        return False


def send_telegram(message: str, chat_id: str) -> bool:
    import os, requests
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        r = requests.post(url, data={"chat_id": chat_id, "text": message}, timeout=10)
        return r.status_code == 200
    except Exception:
        return False


def send_webhook(url: str, payload: dict) -> bool:
    import requests
    try:
        r = requests.post(url, json=payload, timeout=5)
        return r.status_code in (200, 201, 202, 204)
    except Exception:
        return False
