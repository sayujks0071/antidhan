#!/bin/bash
set -e

# Stop systemd timer
echo "Disabling systemd timers..."
systemctl --user stop openalgo-health.timer 2>/dev/null || true
systemctl --user disable openalgo-health.timer 2>/dev/null || true
rm -f ~/.config/systemd/user/openalgo-health.service
rm -f ~/.config/systemd/user/openalgo-health.timer
systemctl --user daemon-reload

# Remove cron
echo "Removing cron jobs..."
# Only update if grep found something to remove to avoid clearing empty crontab if pipe behavior varies
if crontab -l 2>/dev/null | grep -q "healthcheck.py"; then
    crontab -l 2>/dev/null | grep -v "healthcheck.py" | crontab -
fi

echo "✅ Schedulers uninstalled."
