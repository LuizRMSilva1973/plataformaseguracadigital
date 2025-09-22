import os
import time
from typing import Optional
import requests
from sqlalchemy.orm import Session
from .models import IPReputation


def get_ip_reputation(db: Session, ip: str) -> Optional[int]:
    if not ip:
        return None
    ttl = int(os.getenv("IP_REP_TTL_SEC", "86400"))
    now = int(time.time())
    rep = db.get(IPReputation, ip)
    if rep and rep.updated_at and (now - int(rep.updated_at.timestamp())) < ttl:
        return rep.score
    score = None
    source = None
    # Try providers in order depending on keys
    try:
        key = os.getenv("ABUSEIPDB_KEY")
        if key:
            r = requests.get("https://api.abuseipdb.com/api/v2/check", params={"ipAddress": ip, "maxAgeInDays": 60}, headers={"Key": key, "Accept": "application/json"}, timeout=5)
            if r.ok:
                data = r.json().get("data", {})
                score = int(data.get("abuseConfidenceScore", 0))
                source = "abuseipdb"
    except Exception:
        pass
    try:
        if score is None:
            key = os.getenv("IPINFO_KEY")
            if key:
                r = requests.get(f"https://ipinfo.io/{ip}", params={"token": key}, timeout=5)
                if r.ok:
                    data = r.json()
                    # crude heuristic: treat hosting/bogon as higher risk
                    if data.get("bogon"):
                        score = 80
                    else:
                        score = 20
                    source = "ipinfo"
    except Exception:
        pass
    try:
        if score is None:
            key = os.getenv("SHODAN_KEY")
            if key:
                r = requests.get("https://api.shodan.io/shodan/host/" + ip, params={"key": key}, timeout=5)
                if r.status_code == 200:
                    data = r.json()
                    # if many open ports or tags, increase risk
                    ports = data.get("ports", [])
                    score = min(100, 10 + len(ports) * 5)
                    source = "shodan"
    except Exception:
        pass
    # default if none worked
    if score is None:
        score = 0
        source = "none"
    # upsert cache
    if rep:
        rep.score = score
        rep.source = source
    else:
        rep = IPReputation(ip=ip, score=score, source=source)
        db.add(rep)
    db.commit()
    return score

