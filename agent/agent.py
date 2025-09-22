#!/usr/bin/env python3
import argparse
import gzip
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
import socket

import requests


def load_config(path: str):
    import yaml
    with open(path, 'r') as f:
        return yaml.safe_load(f)


def read_tail(path: Path, max_lines: int = 200):
    if not path.exists():
        return []
    try:
        with open(path, 'rb') as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            block = 4096
            data = b""
            while len(data.splitlines()) <= max_lines and f.tell() > 0:
                step = min(block, f.tell())
                f.seek(-step, os.SEEK_CUR)
                data = f.read(step) + data
                f.seek(-step, os.SEEK_CUR)
            lines = data.splitlines()[-max_lines:]
            return [l.decode('utf-8', errors='ignore') for l in lines]
    except Exception:
        return []


def parse_auth_line(line: str):
    # very naive parser for ssh auth failures
    if "Failed password" in line:
        parts = line.split()
        src_ip = parts[-4] if "from" in parts else None
        return {
            "ts": datetime.now(timezone.utc).isoformat(),
            "host": socket.gethostname(),
            "app": "linux-auth",
            "event_type": "auth_failed",
            "src_ip": src_ip,
            "username": "root" if " for root " in line else None,
            "severity": "high",
            "raw": {"message": line}
        }
    return None


def send_batch(api_base: str, token: str, agent_id: str, events: list):
    url = f"{api_base}/v1/ingest"
    batch = {"agent_id": agent_id, "batch_id": str(uuid.uuid4()), "events": events}
    data = json.dumps(batch).encode("utf-8")
    headers = {"Authorization": f"Bearer {token}", "Content-Encoding": "gzip", "Content-Type": "application/json"}
    payload = gzip.compress(data)
    r = requests.post(url, data=payload, headers=headers, timeout=10)
    r.raise_for_status()
    return r.json()


def register(api_base: str, token: str, agent_id: str, host: str):
    url = f"{api_base}/v1/agents/register"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"agent_id": agent_id, "os": os.uname().sysname if hasattr(os, 'uname') else "linux", "version": "0.1.0", "host": host}
    r = requests.post(url, json=payload, headers=headers, timeout=10)
    r.raise_for_status()
    return r.json()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="/etc/digitalsec-agent/config.yaml")
    args = p.parse_args()
    cfg = load_config(args.config)
    api_base = cfg["api_base"].rstrip("/")
    token = cfg["token"]
    agent_id = cfg.get("agent_id") or str(uuid.uuid4())
    cfg_path = Path(args.config)

    host = socket.gethostname()
    try:
        register(api_base, token, agent_id, host)
    except Exception as e:
        print("register failed:", e)

    interval = int(cfg.get("interval_sec", 60))

    while True:
        events = []
        for path in [Path("/var/log/auth.log"), Path("/var/log/secure"), Path("/var/log/syslog")]:
            for line in read_tail(path, max_lines=50):
                e = parse_auth_line(line)
                if e:
                    events.append(e)
        if events:
            try:
                res = send_batch(api_base, token, agent_id, events)
                print("sent:", res)
            except Exception as e:
                print("send failed:", e)
        time.sleep(interval)


if __name__ == "__main__":
    main()
