# Migration & Hardening Fixes

## ✅ Completed Fixes

### 1. Alembic Migration for AuditActionEnum

**File**: `alembic/versions/20251113_add_audit_action_enum.py`

- Creates PostgreSQL enum type `auditactionenum`
- Adds `action` column to `audit_logs` table (nullable, with index)
- Backfills existing rows with `NULL` (app-level values set going forward)

**To apply**:
```bash
alembic upgrade head
```

**To verify**:
```sql
SELECT action, COUNT(*) FROM audit_logs GROUP BY action;
SELECT EXISTS(SELECT 1 FROM pg_type WHERE typname = 'auditactionenum');
```

### 2. Port Override Support

**Files**: `Makefile`, `docker-compose.yml`

- `Makefile`: `PORT` environment variable support
- `docker-compose.yml`: `${PORT:-8000}` for flexible port mapping

**Usage**:
```bash
# Use different port if 8000 is busy
PORT=8010 make paper

# Check what's using port 8000
lsof -nP -iTCP:8000 | grep LISTEN

# Kill process on port 8000 (if needed)
kill -TERM <PID>  # or kill -9 if stubborn
```

### 3. SafeKiteTicker Wrapper

**File**: `packages/core/kite_ws.py`

- Defensive error handling for KiteTicker shutdown
- Handles missing `close()`/`stop()` methods gracefully
- Ignores transient attribute errors during teardown
- Reconnection helper with delay

**Integration**: `MarketDataStream` now uses `SafeKiteTicker` wrapper

### 4. 2-Minute Smoke Test

**File**: `scripts/smoke_check.sh`

- Verifies database schema
- Checks API health and endpoints
- Validates metrics availability
- Tests audit log creation
- Verifies enum type exists

**Usage**:
```bash
make smoke-check
# or
bash scripts/smoke_check.sh
```

## 🚀 Quick Start After Migration

```bash
# 1. Apply migration
alembic upgrade head

# 2. Start on free port (if 8000 busy)
PORT=8010 make paper

# 3. Run smoke test
make smoke-check

# 4. Verify audit logs
psql "$DATABASE_URL" -c "SELECT action, COUNT(*) FROM audit_logs GROUP BY action;"
```

## 📋 Smoke Test Checklist

The smoke test verifies:

- ✅ Database schema (migration applied)
- ✅ API health endpoint
- ✅ State endpoint
- ✅ Risk endpoint
- ✅ Metrics endpoint
- ✅ Flatten endpoint (creates audit log)
- ✅ `audit_logs.action` column exists
- ✅ `auditactionenum` type exists

## 🔧 Troubleshooting

### Port 8000 in use
```bash
# Find process
lsof -nP -iTCP:8000 | grep LISTEN

# Kill gracefully
kill -TERM <PID>

# Or use different port
PORT=8010 make paper
```

### Migration fails
```bash
# Check current revision
alembic current

# Check migration file
cat alembic/versions/20251113_add_audit_action_enum.py

# Manual rollback if needed
alembic downgrade -1
```

### KiteTicker shutdown errors
- Already handled by `SafeKiteTicker` wrapper
- Errors are logged as warnings and ignored during teardown
- No action needed unless you see persistent connection leaks

## 📝 Notes

- Migration sets `action` as nullable initially (existing rows get `NULL`)
- App code should always set `action` for new audit logs
- Enum values must match exactly between `models.py` and migration
- Port override works for both Makefile and docker-compose

