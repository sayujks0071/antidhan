# Quick Start After Migration

## 🚀 Run This Now

```bash
# Option 1: Automated checklist (recommended)
make migration-checklist

# Option 2: Manual steps
alembic upgrade head
PORT=8010 make paper
make smoke-check
```

## 📋 What Gets Checked

### 1. Migration Applied
- Runs `alembic upgrade head`
- Verifies enum type created
- Checks column exists

### 2. Port Availability
- Checks if port 8000 is free
- Suggests alternative port if busy
- Shows how to kill blocking process

### 3. Database Verification
- Verifies `auditactionenum` type exists
- Checks `audit_logs.action` column
- Shows recent audit log entries

### 4. SafeKiteTicker Test
- Tests wrapper with different client shapes
- Verifies graceful shutdown handling

## 🔧 Manual Sanity Checks

### Verify Enum & Column (SQL)

```sql
-- Enum type present
SELECT typname FROM pg_type WHERE typname='auditactionenum';

-- Column present and using enum
SELECT column_name, udt_name
FROM information_schema.columns
WHERE table_name='audit_logs' AND column_name='action';

-- Recent audit rows
SELECT action, count(*) FROM audit_logs GROUP BY action ORDER BY 2 DESC LIMIT 10;
```

### Test API Endpoints

```bash
# Set your port
PORT=8010

# Health check
curl -s http://localhost:${PORT}/health

# State
curl -s http://localhost:${PORT}/state | jq

# Risk
curl -s http://localhost:${PORT}/risk | jq

# Metrics
curl -s http://localhost:${PORT}/metrics | grep -E '^trader_' | head
```

### Test SafeKiteTicker

```bash
python3 - <<'PY'
from types import SimpleNamespace
from packages.core.kite_ws import SafeKiteTicker

# Simulate different client shapes
for obj in [SimpleNamespace(close=lambda: None),
            SimpleNamespace(stop=lambda: None),
            SimpleNamespace()]:
    SafeKiteTicker(obj).stop()
print("✅ SafeKiteTicker teardown OK")
PY
```

## 🐛 Troubleshooting

### Port 8000 in Use

```bash
# Find process
lsof -nP -iTCP:8000 | grep LISTEN

# Kill gracefully
kill -TERM <PID>

# Or use different port
PORT=8010 make paper
```

### Alembic Not Found

```bash
# Activate virtual environment (if using)
source venv/bin/activate

# Or install dependencies
pip install -r requirements.txt

# Then run
python -m alembic upgrade head
```

### Database Connection Issues

```bash
# Check DATABASE_URL is set
echo $DATABASE_URL

# Default: postgresql://trader:trader@localhost:5432/aitrapp

# Test connection
psql "$DATABASE_URL" -c "SELECT 1;"
```

## ✅ Success Indicators

After running the checklist, you should see:

- ✅ Migration applied successfully
- ✅ Enum type exists in database
- ✅ Column exists and is typed correctly
- ✅ SafeKiteTicker wrapper works
- ✅ API endpoints respond (if API is running)
- ✅ Metrics available (if orchestrator initialized)

## 🎯 Next Steps

1. **Start API**: `PORT=8010 make paper`
2. **Run smoke test**: `make smoke-check`
3. **Run quick sanity**: `make quick-sanity`
4. **Start trading**: `make paper-e2e` (pre-open test)

## 💡 Pro Tips

- **Port override**: Always use `PORT=8010` if 8000 is busy
- **Mac lsof**: `lsof -nP -iTCP:8000 | grep LISTEN` to find stray servers
- **Enum rollbacks**: Postgres won't drop enum if column uses it (downgrade handles this)
- **Docker compose**: `${PORT:-8000}` syntax works for port mapping

