#!/bin/bash
# Install Crontab entry (fallback)

SCRIPT_DIR=$(cd $(dirname $0) && pwd)
SCRIPT_PATH="$SCRIPT_DIR/healthcheck.py"
PYTHON_EXEC=$(which python3)

echo "Installing Cron job..."

# Remove existing entry to avoid duplicates
crontab -l 2>/dev/null | grep -v "healthcheck.py" > /tmp/cron_backup

# Add new entry
echo "*/5 * * * * $PYTHON_EXEC $SCRIPT_PATH >> /tmp/openalgo_cron.log 2>&1" >> /tmp/cron_backup

crontab /tmp/cron_backup
rm /tmp/cron_backup

echo "✅ Cron job installed."
crontab -l | grep healthcheck.py
