# Audit Log Retention

Keep the database small and fast with proper audit log retention policies.

## 📊 Current State

- Audit logs are stored in `audit_logs` table
- No automatic retention policy currently
- Logs accumulate indefinitely

## 🎯 Retention Strategy

### Recommended Approach

1. **Hot Storage (PostgreSQL)**: Keep last 30 days
2. **Warm Storage (S3/Archive)**: Keep last 1 year
3. **Cold Storage (Long-term archive)**: Keep indefinitely (compressed)

### Implementation

#### 1. Add Index for Performance

```sql
CREATE INDEX IF NOT EXISTS ix_audit_logs_ts ON audit_logs (ts DESC);
```

This index helps with:
- Fast queries by timestamp
- Efficient pruning of old records
- Better performance on time-range queries

#### 2. Nightly Prune Script

Create `scripts/prune_audit_logs.py`:

```python
"""Prune old audit logs"""
import sys
from datetime import datetime, timedelta
from packages.storage.database import get_db_session
from packages.storage.models import AuditLog

RETENTION_DAYS = 30  # Keep last 30 days in DB

def prune_audit_logs():
    """Prune audit logs older than retention period"""
    cutoff_date = datetime.utcnow() - timedelta(days=RETENTION_DAYS)
    
    with get_db_session() as db:
        deleted = db.query(AuditLog).filter(AuditLog.ts < cutoff_date).delete()
        db.commit()
        print(f"Deleted {deleted} audit log entries older than {RETENTION_DAYS} days")
    
    return deleted

if __name__ == "__main__":
    prune_audit_logs()
```

#### 3. Archive to S3 (Optional)

Before pruning, archive to S3:

```python
"""Archive audit logs to S3 before pruning"""
import json
import boto3
from datetime import datetime, timedelta
from packages.storage.database import get_db_session
from packages.storage.models import AuditLog

S3_BUCKET = "aitrapp-audit-logs"
RETENTION_DAYS = 30

def archive_audit_logs():
    """Archive old audit logs to S3 before pruning"""
    cutoff_date = datetime.utcnow() - timedelta(days=RETENTION_DAYS)
    
    s3 = boto3.client('s3')
    
    with get_db_session() as db:
        logs = db.query(AuditLog).filter(AuditLog.ts < cutoff_date).all()
        
        # Group by date for efficient archiving
        logs_by_date = {}
        for log in logs:
            date_key = log.ts.date().isoformat()
            if date_key not in logs_by_date:
                logs_by_date[date_key] = []
            logs_by_date[date_key].append({
                "id": log.id,
                "ts": log.ts.isoformat(),
                "action": log.action.value if hasattr(log.action, 'value') else str(log.action),
                "message": log.message,
                "details": log.details if hasattr(log, 'details') else log.data,
            })
        
        # Upload to S3
        for date_key, logs_data in logs_by_date.items():
            key = f"audit_logs/{date_key}.json"
            s3.put_object(
                Bucket=S3_BUCKET,
                Key=key,
                Body=json.dumps(logs_data, indent=2),
                ContentType='application/json'
            )
            print(f"Archived {len(logs_data)} logs to s3://{S3_BUCKET}/{key}")
        
        # Prune after archiving
        deleted = db.query(AuditLog).filter(AuditLog.ts < cutoff_date).delete()
        db.commit()
        print(f"Pruned {deleted} audit log entries from database")
    
    return len(logs)

if __name__ == "__main__":
    archive_audit_logs()
```

#### 4. Add to Cron/Daily Job

Add to your daily post-close routine:

```bash
# In scripts/post_close_hygiene.sh or similar
python scripts/prune_audit_logs.py
# Or with archiving:
python scripts/archive_audit_logs.py
```

## 📋 Retention Policy

| Period | Storage | Access | Purpose |
|--------|---------|--------|---------|
| 0-30 days | PostgreSQL | Fast queries | Active monitoring, debugging |
| 30-365 days | S3/Archive | On-demand | Compliance, analysis |
| 365+ days | Cold storage | Archive | Long-term compliance |

## 🔍 Monitoring

Track audit log table size:

```sql
SELECT 
    pg_size_pretty(pg_total_relation_size('audit_logs')) as total_size,
    pg_size_pretty(pg_relation_size('audit_logs')) as table_size,
    COUNT(*) as row_count,
    MIN(ts) as oldest_log,
    MAX(ts) as newest_log
FROM audit_logs;
```

## ⚠️ Considerations

1. **Compliance**: Check regulatory requirements for audit log retention
2. **Performance**: Large tables can slow down queries
3. **Backups**: Ensure archived logs are included in backup strategy
4. **Access**: Make sure archived logs are accessible when needed
5. **Cost**: S3 storage costs vs database storage costs

## 🚀 Quick Start

1. **Add index**:
   ```sql
   CREATE INDEX IF NOT EXISTS ix_audit_logs_ts ON audit_logs (ts DESC);
   ```

2. **Run prune manually**:
   ```bash
   python scripts/prune_audit_logs.py
   ```

3. **Add to daily job**:
   ```bash
   # Add to post-close script
   make post-close  # Should include pruning
   ```

4. **Monitor table size**:
   ```bash
   psql "$DATABASE_URL" -c "SELECT pg_size_pretty(pg_total_relation_size('audit_logs'));"
   ```

