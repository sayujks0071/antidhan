#!/bin/bash
# Remove Systemd User Timer for OpenAlgo Healthcheck

echo "Stopping Systemd User Service..."
systemctl --user stop openalgo-health.timer
systemctl --user disable openalgo-health.timer
systemctl --user stop openalgo-health.service
systemctl --user disable openalgo-health.service
rm ~/.config/systemd/user/openalgo-health.timer
rm ~/.config/systemd/user/openalgo-health.service
systemctl --user daemon-reload
echo "✅ Systemd user timer removed."

echo "Removing Cron job..."
crontab -l | grep -v "healthcheck.py" > /tmp/cron_backup
crontab /tmp/cron_backup
rm /tmp/cron_backup
echo "✅ Cron job removed."
