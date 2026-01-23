# Backup Strategy

Ensure data safety with proper backup and restore procedures.

## 📋 Backup Requirements

### Daily Backups
- Full database dump (`pg_dump`)
- Include all tables (signals, decisions, orders, positions, trades, audit_logs)
- Compressed for storage efficiency

### Weekly Backups
- WAL/Archive snapshot
- Point-in-time recovery capability
- Test restore procedure

## 🔧 Implementation

### 1. Daily Database Dump

Create `scripts/daily_backup.sh`:

```bash
#!/usr/bin/env bash
# Daily database backup
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
DATE=$(date +%Y%m%d)
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DATABASE_URL="${DATABASE_URL:-postgresql+psycopg2://trader:trader@localhost:5432/aitrapp}"

mkdir -p "$BACKUP_DIR"

# Extract connection details
DB_CONN="${DATABASE_URL#postgresql+psycopg2://}"

# Full database dump (compressed)
BACKUP_FILE="$BACKUP_DIR/aitrapp_backup_${TIMESTAMP}.sql.gz"

echo "Creating backup: $BACKUP_FILE"
pg_dump "$DB_CONN" | gzip > "$BACKUP_FILE"

# Keep only last 7 days of daily backups
find "$BACKUP_DIR" -name "aitrapp_backup_*.sql.gz" -mtime +7 -delete

echo "✅ Backup complete: $BACKUP_FILE"
echo "Size: $(du -h "$BACKUP_FILE" | cut -f1)"
```

### 2. Weekly Archive Snapshot

Create `scripts/weekly_backup.sh`:

```bash
#!/usr/bin/env bash
# Weekly archive snapshot
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups/archive}"
DATE=$(date +%Y%m%d)
DATABASE_URL="${DATABASE_URL:-postgresql+psycopg2://trader:trader@localhost:5432/aitrapp}"

mkdir -p "$BACKUP_DIR"

DB_CONN="${DATABASE_URL#postgresql+psycopg2://}"

# Weekly snapshot (uncompressed for easier inspection)
SNAPSHOT_FILE="$BACKUP_DIR/aitrapp_snapshot_${DATE}.sql"

echo "Creating weekly snapshot: $SNAPSHOT_FILE"
pg_dump "$DB_CONN" --format=plain > "$SNAPSHOT_FILE"

# Compress after creation
gzip "$SNAPSHOT_FILE"

# Keep last 12 weeks
find "$BACKUP_DIR" -name "aitrapp_snapshot_*.sql.gz" -mtime +84 -delete

echo "✅ Weekly snapshot complete: ${SNAPSHOT_FILE}.gz"
```

### 3. Test Restore Procedure

Create `scripts/test_restore.sh`:

```bash
#!/usr/bin/env bash
# Test restore from backup
set -euo pipefail

BACKUP_FILE="${1:-}"
TEST_DB="${TEST_DB:-aitrapp_test_restore}"

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: $0 <backup_file.sql.gz>"
    exit 1
fi

echo "Testing restore from: $BACKUP_FILE"

# Create test database
createdb "$TEST_DB" || echo "Test DB may already exist"

# Restore backup
if [[ "$BACKUP_FILE" == *.gz ]]; then
    gunzip -c "$BACKUP_FILE" | psql "$TEST_DB"
else
    psql "$TEST_DB" < "$BACKUP_FILE"
fi

# Verify restore
echo "Verifying restore..."
psql "$TEST_DB" -c "SELECT COUNT(*) FROM audit_logs;"
psql "$TEST_DB" -c "SELECT COUNT(*) FROM orders;"
psql "$TEST_DB" -c "SELECT COUNT(*) FROM positions;"

echo "✅ Restore test complete"
echo "Clean up: dropdb $TEST_DB"
```

### 4. Add to Cron

```bash
# Daily backup at 2 AM
0 2 * * * /path/to/scripts/daily_backup.sh

# Weekly backup on Sunday at 3 AM
0 3 * * 0 /path/to/scripts/weekly_backup.sh
```

Or add to your post-close script:

```bash
# In scripts/post_close_hygiene.sh
bash scripts/daily_backup.sh
```

## 🔄 Restore Procedure

### Full Restore

```bash
# Stop application
pkill -f uvicorn

# Drop existing database (⚠️ DESTRUCTIVE)
dropdb aitrapp

# Create fresh database
createdb aitrapp

# Restore from backup
gunzip -c backups/aitrapp_backup_YYYYMMDD_HHMMSS.sql.gz | psql aitrapp

# Verify restore
psql aitrapp -c "SELECT COUNT(*) FROM audit_logs;"

# Restart application
make paper
```

### Point-in-Time Recovery

For point-in-time recovery, you'll need:
1. Base backup
2. WAL archives
3. PostgreSQL configured for WAL archiving

See PostgreSQL documentation for PITR setup.

## 📊 Backup Monitoring

### Check Backup Status

```bash
# List recent backups
ls -lh backups/*.sql.gz | tail -10

# Check backup size
du -sh backups/

# Verify backup integrity
gunzip -t backups/aitrapp_backup_*.sql.gz
```

### Backup Health Check

Add to monitoring:

```bash
# Check if backup exists for today
BACKUP_TODAY=$(find backups -name "aitrapp_backup_$(date +%Y%m%d)*.sql.gz" | head -1)
if [ -z "$BACKUP_TODAY" ]; then
    echo "⚠️  No backup found for today"
    exit 1
fi

# Check backup size (should be > 0)
SIZE=$(stat -f%z "$BACKUP_TODAY" 2>/dev/null || stat -c%s "$BACKUP_TODAY" 2>/dev/null)
if [ "$SIZE" -eq 0 ]; then
    echo "⚠️  Backup file is empty"
    exit 1
fi

echo "✅ Backup health check passed"
```

## 🚀 Quick Start

1. **Create backup directory**:
   ```bash
   mkdir -p backups/archive
   ```

2. **Run daily backup**:
   ```bash
   bash scripts/daily_backup.sh
   ```

3. **Test restore**:
   ```bash
   bash scripts/test_restore.sh backups/aitrapp_backup_YYYYMMDD_HHMMSS.sql.gz
   ```

4. **Add to automation**:
   ```bash
   # Add to post-close script or cron
   ```

## ⚠️ Important Notes

1. **Test restores regularly**: Don't wait for a disaster to test
2. **Off-site storage**: Consider storing backups in S3 or another location
3. **Encryption**: Encrypt backups if they contain sensitive data
4. **Retention**: Define retention policy (7 days daily, 12 weeks weekly)
5. **Monitoring**: Alert if backups fail
6. **Documentation**: Keep restore procedures documented and tested

