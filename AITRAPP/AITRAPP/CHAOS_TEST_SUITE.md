# 🧪 Chaos Test Suite

Production-grade resilience testing for AITRAPP.

## Overview

The chaos test suite verifies that the system gracefully handles failures and automatically recovers without crashes or manual intervention.

## Test Scripts

### 1. Leader Lock Chaos Test (`chaos_test_leader_lock.sh`)

**Purpose:** Verifies self-healing leader lock mechanism.

**What it tests:**
- Leader lock loss detection
- Automatic pause on lock loss
- Auto-reacquire with exponential backoff
- Automatic resume on re-acquisition
- Readiness endpoint flips (503 → 200)
- No process crashes

**PASS/FAIL Criteria:**
- ✅ On Redis stop: `/ready` → 503, `trader_is_leader` → 0, orchestrator paused
- ✅ Within recovery window: `/ready` → 200, `trader_is_leader` → 1, orchestrator resumed
- ✅ All three heartbeats < 5s
- ✅ No process crash; no manual restarts required

**Usage:**
```bash
# Interactive (with prompts)
bash scripts/chaos_test_leader_lock.sh

# Non-interactive (auto-proceed)
NONINTERACTIVE=1 bash scripts/chaos_test_leader_lock.sh

# With auto-abort on failure
NONINTERACTIVE=1 PAUSE_ON_FAIL=1 bash scripts/chaos_test_leader_lock.sh
```

**Evidence:** Records test results to `reports/chaos/leader_lock_<timestamp>.log`

### 2. Postgres Blip Test (`chaos_test_postgres.sh`)

**Purpose:** Verifies persistence errors don't crash the app.

**What it tests:**
- API stays up during Postgres outage
- API recovers after Postgres restart
- Idempotency holds after DB returns

**Usage:**
```bash
bash scripts/chaos_test_postgres.sh
```

### 3. Rate-Limit Spike Test (`chaos_test_rate_limit.sh`)

**Purpose:** Verifies throttle queue depth handling and idempotency.

**What it tests:**
- Throttle queue depth rises and returns to 0
- No duplicate `client_order_id`
- System handles burst traffic gracefully

**Usage:**
```bash
bash scripts/chaos_test_rate_limit.sh
```

## Configuration Flags

### `NONINTERACTIVE=1`
- Auto-proceeds without user prompts
- Useful for CI/CD pipelines
- Default: `0` (interactive)

### `PAUSE_ON_FAIL=1`
- Calls `make abort` if test fails
- Ensures system is in safe state
- Default: `0` (no auto-abort)

### `API=http://localhost:8000`
- Override API endpoint
- Default: `http://localhost:8000`

### `REDIS_CONTAINER=redis`
- Override Redis container name
- Default: `redis`

### `HEARTBEAT_MAX=5`
- Maximum heartbeat threshold (seconds)
- Default: `5`

### `WAIT_READY_TIMEOUT=90`
- Maximum wait time for `/ready` (seconds)
- Default: `90`

## Evidence Recording

All tests record evidence to `reports/chaos/` directory:

- Timestamped log files
- Metrics snapshots
- Test results (PASS/FAIL)
- Heartbeat values
- Leader lock state transitions

Example log format:
```
leader_lock_chaos_test,2025-11-13T14-30-00
leader_before,1
leader_after_stop,0
leader_after_recovery,1
ready_before,ready
ready_after_stop,not_ready
ready_after_recovery,ready
scan_hb,1.2
order_hb,0.8
md_hb,0.5
test_result,PASS
```

## Helper Functions

The scripts include helper functions for assertions:

- `jqval()` - Extract JSON values from API responses
- `metric()` - Extract Prometheus metric values
- `wait_ready()` - Wait for `/ready` endpoint to return 200
- `assert_paused()` - Verify orchestrator is paused
- `assert_resumed()` - Verify orchestrator is resumed
- `snapshot_metrics()` - Capture current metrics state

## Running All Tests

```bash
# Run all chaos tests
bash scripts/chaos_test_leader_lock.sh
bash scripts/chaos_test_postgres.sh
bash scripts/chaos_test_rate_limit.sh

# Or in CI/CD (non-interactive)
NONINTERACTIVE=1 PAUSE_ON_FAIL=1 bash scripts/chaos_test_leader_lock.sh
```

## Expected Behavior

### Leader Lock Test Flow

1. **Baseline:** Leader=1, Ready=200, Paused=false
2. **Stop Redis:** Leader=0, Ready=503, Paused=true, API healthy
3. **Restart Redis:** Wait for auto-reacquire
4. **Recovery:** Leader=1, Ready=200, Paused=false, Heartbeats < 5s

### Key Assertions

- ✅ API never crashes (health stays "healthy")
- ✅ Trading pauses immediately on lock loss
- ✅ Trading resumes automatically on re-acquisition
- ✅ Readiness endpoint correctly reflects system state
- ✅ All heartbeats remain fresh (< 5s)

## Troubleshooting

### Test fails at "leader should be 0"
- Check if Redis actually stopped
- Wait longer for lock to expire (TTL is 30s)
- Check Redis connection in logs

### Test fails at "leader should be 1"
- Check if Redis actually restarted
- Wait longer for auto-reacquire (up to 90s)
- Check orchestrator logs for re-acquire attempts

### API crashes during test
- This is a critical failure - investigate immediately
- Check logs for unhandled exceptions
- Verify graceful error handling in code

## Integration with CI/CD

Add to your CI pipeline:

```yaml
# .github/workflows/chaos-tests.yml
- name: Run chaos tests
  run: |
    NONINTERACTIVE=1 bash scripts/chaos_test_leader_lock.sh
    NONINTERACTIVE=1 bash scripts/chaos_test_postgres.sh
```

## Next Steps

- Add broker token expiry test
- Add WebSocket reconnection test
- Add network partition simulation
- Add memory/CPU stress tests

