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

# Ensure log dir exists
mkdir -p "$REPO_ROOT/logs"

CRON_CMD="*/5 * * * * $PYTHON_BIN $HEALTH_SCRIPT >> $REPO_ROOT/logs/cron_health.log 2>&1"

# Check if already exists
if crontab -l 2>/dev/null | grep -Fq "$HEALTH_SCRIPT"; then
    echo "Cron job already exists."
    exit 0
fi

# Add job
(crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -
echo "✅ Cron job added."
