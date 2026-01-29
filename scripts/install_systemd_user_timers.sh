#!/bin/bash
set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
HEALTH_SCRIPT="$REPO_ROOT/scripts/healthcheck.py"

# Detect Python
if [ -f "$REPO_ROOT/openalgo/.venv/bin/python" ]; then
    PYTHON_BIN="$REPO_ROOT/openalgo/.venv/bin/python"
elif [ -f "$REPO_ROOT/.venv/bin/python" ]; then
    PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
else
    PYTHON_BIN=$(which python3)
fi

echo "Using Python: $PYTHON_BIN"

# Ensure config dir exists
mkdir -p ~/.config/systemd/user/

# Create Service
SERVICE_FILE=~/.config/systemd/user/openalgo-health.service
echo "Creating service file at $SERVICE_FILE"
cat > "$SERVICE_FILE" << EOF
[Unit]
Description=OpenAlgo Health Check
After=network.target

[Service]
Type=oneshot
ExecStart=$PYTHON_BIN $HEALTH_SCRIPT
WorkingDirectory=$REPO_ROOT
Environment=PATH=$PATH
EOF

# Create Timer
TIMER_FILE=~/.config/systemd/user/openalgo-health.timer
echo "Creating timer file at $TIMER_FILE"
cat > "$TIMER_FILE" << EOF
[Unit]
Description=Run OpenAlgo Health Check every 5 minutes

[Timer]
OnBootSec=5min
OnUnitActiveSec=5min

[Install]
WantedBy=timers.target
EOF

# Reload and Enable
echo "Reloading systemd user daemon..."
systemctl --user daemon-reload
echo "Enabling timer..."
systemctl --user enable --now openalgo-health.timer

echo "✅ Systemd user timer installed and started."
systemctl --user list-timers --all | grep openalgo
