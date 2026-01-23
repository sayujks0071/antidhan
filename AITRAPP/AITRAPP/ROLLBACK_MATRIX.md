# 🚨 Fast Rollback Matrix

Immediate actions for common failure scenarios.

## Alert-Based Rollback

**Any alert from `ops/alerts.yml`** → `abort`
```bash
make abort
# Or: pause && killnow && paper
```

## Heartbeat Failures

**Heartbeat > 5s for 1m** → `abort`
```bash
# Check heartbeats
curl -s :8000/metrics | grep -E '^trader_(marketdata_heartbeat_seconds|order_stream_heartbeat_seconds|scan_heartbeat_seconds)'

# If any > 5s for 1 minute:
make abort
```

## Schema/Enum Drift

**ENUM/schema drift** (prelive gate would've caught it) → Fix and restart
```bash
# Apply migration
alembic upgrade head

# Restart API
make paper  # or make live-switch
```

## Token Expiry

**Token expiry / 401** → Ensure auto-rotate fired; if repeated, abort and rotate manually
```bash
# Check for token refresh retries
curl -s :8000/metrics | grep 'trader_retries_total{type="token_refresh"}'

# If high, check token expiry
# Rotate token manually if needed
# Then: make abort && (fix token) && make live-switch
```

## Common Failure Signatures → Fixes

### Scan Heartbeat Drifting

**Symptom:** Scan heartbeat drifting while other two are fresh

**Cause:** Supervisor task got cancelled or never scheduled

**Fix:**
```bash
# Check supervisor state
curl -s :8000/debug/supervisor/status | jq

# If state=0, start it
curl -X POST :8000/debug/supervisor/start | jq

# Verify
curl -s :8000/metrics | grep -E '^trader_(scan_supervisor_state|scan_ticks_total)'
# Should show: state=1, ticks_total incrementing
```

### Metrics Frozen

**Symptom:** Metrics frozen but API healthy

**Cause:** Multiple uvicorn workers without Prometheus multiprocess

**Fix:**
```bash
# Run with single worker
uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --workers 1

# Or set up Prometheus multiprocess mode properly
export PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus
```

### Duplicate SL/TP on Restart

**Symptom:** Duplicate stop-loss/take-profit orders on restart

**Cause:** OCO guard not working or recovery not re-arming watchers

**Fix:**
- Confirm single-flight OCO guard in `OCOManager.on_entry_fill()`
- Verify `_recover_open_positions()` re-arms watchers before live trading
- Check for duplicate `client_order_id` in database

### /flatten Slow

**Symptom:** `/flatten` > 2s

**Cause:** Order stream heartbeat stale or broker throttle

**Fix:**
```bash
# Check order stream heartbeat
curl -s :8000/metrics | grep 'trader_order_stream_heartbeat_seconds'

# Check rate limit queue depth
curl -s :8000/metrics | grep 'trader_throttle_queue_depth'

# If high, back off child placement concurrency
# Or check broker connectivity
```

## Emergency Abort

**Immediate abort macro:**
```bash
make abort
# Or manually:
curl -X POST :8000/pause
curl -X POST :8000/flatten -H 'Content-Type: application/json' -d '{"reason":"emergency"}'
curl -X POST :8000/mode -H 'Content-Type: application/json' -d '{"mode":"PAPER"}'
```

