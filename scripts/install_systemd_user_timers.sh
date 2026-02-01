#!/bin/bash
# Install Systemd User Timer for OpenAlgo Healthcheck

mkdir -p ~/.config/systemd/user
SCRIPT_DIR=$(cd $(dirname $0) && pwd)
SCRIPT_PATH="$SCRIPT_DIR/healthcheck.py"
PYTHON_EXEC=$(which python3)

SERVICE_FILE=~/.config/systemd/user/openalgo-health.service
TIMER_FILE=~/.config/systemd/user/openalgo-health.timer

echo "Installing Systemd User Service..."

cat <<EOF > $SERVICE_FILE
[Unit]
Description=OpenAlgo Health Check

[Service]
ExecStart=$PYTHON_EXEC $SCRIPT_PATH
WorkingDirectory=$SCRIPT_DIR
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF

cat <<EOF > $TIMER_FILE
[Unit]
Description=Run OpenAlgo Health Check every 5 minutes

[Timer]
OnBootSec=5min
OnUnitActiveSec=5min
Unit=openalgo-health.service

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable openalgo-health.timer
systemctl --user start openalgo-health.timer

echo "✅ Systemd user timer installed and started."
systemctl --user list-timers --all | grep openalgo
