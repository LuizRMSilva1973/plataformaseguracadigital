#!/usr/bin/env bash
set -euo pipefail

API="http://localhost:8000"
TENANT="demo"
TOKEN="demo-token"
CHANNEL="stable"
SRC_DIR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --api) API="$2"; shift 2;;
    --tenant) TENANT="$2"; shift 2;;
    --token) TOKEN="$2"; shift 2;;
    --channel) CHANNEL="$2"; shift 2;;
    --source-dir) SRC_DIR="$2"; shift 2;;
    *) echo "Unknown arg: $1"; exit 1;;
  esac
done

USER="digitalsec"
INSTALL_DIR="/opt/digitalsec-agent"
CONF_DIR="/etc/digitalsec-agent"

id -u "$USER" >/dev/null 2>&1 || sudo useradd -r -s /usr/sbin/nologin "$USER"
sudo mkdir -p "$INSTALL_DIR" "$CONF_DIR"

if [[ -n "$SRC_DIR" && -f "$SRC_DIR/agent/agent.py" ]]; then
  sudo cp "$SRC_DIR/agent/agent.py" "$INSTALL_DIR/agent.py"
else
  echo "Please provide --source-dir pointing to repository root to copy agent.py"
  exit 1
fi

cat <<EOF | sudo tee "$CONF_DIR/config.yaml" >/dev/null
api_base: "$API"
tenant_id: "$TENANT"
token: "$TOKEN"
interval_sec: 60
EOF

sudo chown -R $USER:$USER "$INSTALL_DIR" "$CONF_DIR"
sudo chmod 750 "$INSTALL_DIR"

cat <<'EOF' | sudo tee /etc/systemd/system/digitalsec-agent.service >/dev/null
[Unit]
Description=DigitalSec Agent
After=network-online.target
Wants=network-online.target

[Service]
User=digitalsec
Group=digitalsec
ExecStart=/usr/bin/env python3 /opt/digitalsec-agent/agent.py --config /etc/digitalsec-agent/config.yaml
Restart=always
RestartSec=15

[Install]
WantedBy=multi-user.target
EOF

cat <<'EOF' | sudo tee /etc/systemd/system/digitalsec-agent.timer >/dev/null
[Unit]
Description=DigitalSec Agent Heartbeat Timer

[Timer]
OnBootSec=30s
OnUnitActiveSec=60s
Unit=digitalsec-agent.service

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now digitalsec-agent.service || true
sudo systemctl enable --now digitalsec-agent.timer || true

echo "Agent installed. Service: digitalsec-agent.service"

