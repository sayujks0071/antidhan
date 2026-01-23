# 🧹 Production Hygiene

One-time and ongoing maintenance tasks.

## Dependency Management

**Keep installing from `requirements.lock` on prod nodes to avoid drift.**

```bash
# Generate lock file
pip freeze > requirements.lock

# Install from lock file
pip install -r requirements.lock
```

## Audit Log Retention

**Nightly audit log retention job:**
- Hot: 30 days (keep in database)
- Warm: S3 archival 1 year
- Cold: Archive older than 1 year

See `docs/AUDIT_LOG_RETENTION.md` for details.

## Backups

**Daily:**
```bash
# Daily pg_dump
pg_dump "${DATABASE_URL#postgresql+psycopg2://}" > backups/daily_$(date +%Y%m%d).sql
```

**Weekly:**
```bash
# Weekly snapshot
pg_dump "${DATABASE_URL#postgresql+psycopg2://}" > backups/weekly_$(date +%Y%m%d).sql
```

**Monthly:**
- Test restore from backup
- Verify data integrity

## Configuration

- Keep `config/app_config.yaml` versioned
- Use environment variables for secrets
- Never commit `.env` files
- Rotate tokens regularly

## Monitoring

- Set up Prometheus alerts (see `ops/alerts.yml`)
- Configure Telegram/Slack notifications
- Review metrics daily
- Check logs for anomalies

## Health Checks

**Daily:**
- `/health` endpoint
- `/ready` endpoint
- Supervisor status
- Heartbeat freshness

**Weekly:**
- Database reconciliation
- Backup verification
- Token rotation check
- Dependency updates

