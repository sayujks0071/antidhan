# Day-1 PAPER Burn-In Status Report
**Date:** 2025-11-13  
**Session:** PAPER Day-1  
**Analyst:** AI Pair-Programmer

---

## A) What's Built

### System Architecture

**Core Trading Pipeline:**
```
MarketDataStream (WebSocket) → Strategies → Ranker → RiskManager → ExecutionEngine → OCOManager → OrderWatcher → Persistence
```

**Components Implemented:**

1. **TradingOrchestrator** (`packages/core/orchestrator.py`)
   - Main loop: 5s scan cycle via `_scan_supervisor()`
   - Pipeline: Signals → Ranking → Risk → Execution → OCO
   - State: 1,088 scan ticks, supervisor running (state=1)
   - Heartbeats: All < 5s ✅

2. **Strategies** (4 implemented)
   - ORBStrategy (`packages/core/strategies/orb.py`)
   - TrendPullbackStrategy (`packages/core/strategies/trend_pullback.py`)
   - OptionsRankerStrategy (`packages/core/strategies/options_ranker.py`)
   - IronCondorStrategy (`packages/core/strategies/iron_condor.py`)

3. **Risk Management** (`packages/core/risk.py`)
   - Per-trade risk limits
   - Portfolio heat monitoring
   - Daily loss limits
   - Freeze quantity checks

4. **OCO Manager** (`packages/core/oco.py`)
   - Entry + Stop + TP order groups
   - Sibling cancellation on fill
   - Crash-safe recovery

5. **OrderWatcher** (`packages/core/order_watcher.py`)
   - Polls broker for order updates
   - Calls orchestrator callbacks on fills
   - Updates heartbeats

6. **Persistence** (`packages/storage/models.py`)
   - 8 models: Instrument, Signal, Decision, Order, Position, Trade, RiskEvent, AuditLog
   - Alembic migrations: 2 applied (enum + schema alignment)
   - Dual-schema compatibility (details/data columns)

7. **Leader Lock** (`packages/core/leader_lock.py`)
   - Redis-based single-instance guard
   - Self-healing with exponential backoff
   - **BUG FOUND**: Redis client compatibility issue (see Issues)

8. **Heartbeats** (`packages/core/heartbeats.py`)
   - Market data: 0.4s ✅
   - Order stream: 1.0s ✅
   - Scan loop: 0.5-3.5s ✅

9. **FastAPI Control Plane** (`apps/api/main.py`)
   - 20 endpoints: `/health`, `/ready`, `/state`, `/positions`, `/risk`, `/metrics`, `/flatten`, etc.
   - Debug endpoints: `/debug/scan-once`, `/debug/supervisor/status`
   - Graceful shutdown

10. **Ops & Monitoring**
    - Prometheus metrics (38 counters/gauges/histograms)
    - Alert rules (`ops/alerts.yml`)
    - Pre-live gate (`scripts/prelive_gate.sh`)
    - Chaos tests (`scripts/chaos_test_*.sh`)
    - Day-1 scorer (`scripts/score_day1.sh`)

**Persistence Status:**
- ✅ Models: 8 tables defined
- ✅ Migrations: 2 applied (head: `20251113_align_auditlog_schema`)
- ✅ Enum alignment: `AuditActionEnum` in DB
- ✅ JSONB: `details` column exists
- ⚠️ DATABASE_URL not set (DB checks skipped)

---

## B) Today's PAPER Report (Evidence-Backed)

### Readiness & Heartbeats Timeline

**Current Metrics (20:08 IST):**
```
trader_is_leader: 0.0 ❌ (expected 1)
trader_marketdata_heartbeat_seconds: 0.38s ✅
trader_order_stream_heartbeat_seconds: 1.0s ✅
trader_scan_heartbeat_seconds: 0.56s ✅
trader_scan_ticks_total: 1,088 ✅
trader_scan_supervisor_state: 1.0 (running) ✅
trader_kill_switch_total{reason="leader_lock_lost"}: 187 ❌
```

**Readiness Endpoint:**
```json
{
  "detail": "Readiness check error: 503: {
    'status': 'not_ready',
    'leader': 0.0,
    'marketdata_heartbeat': 0.41,
    'order_stream_heartbeat': 1.02,
    'scan_heartbeat': 3.49,
    'heartbeat_max': 5.0
  }"
}
```

**State:**
```json
{
  "mode": "PAPER",
  "is_paused": true,
  "is_market_open": false,
  "positions_count": 0,
  "trades_today": 0
}
```

### Orders/Decisions/OCO Totals

**Metrics:**
- `trader_orders_placed_total`: Not visible (likely 0)
- `trader_oco_children_created_total`: 0.0 ❌
- `trader_scan_ticks_total`: 1,088 ✅

**API Queries:**
- Positions: 0 ✅
- Orders: 2 (open orders found)

### Reconcile Results

**Status:** ⚠️ DATABASE_URL not set - DB checks skipped

**Expected Checks:**
- Duplicate `client_order_id`: N/A (DB unavailable)
- Orphan OCO children: N/A (DB unavailable)

### Paper E2E Test

**Result:** ✅ PASSED (with warnings)

```
✅ Flatten command accepted
✅ All positions flattened
✅ No orphaned OCO groups
✅ All signals have decisions
⚠️  Found 1 decisions without orders
✅ Order latency histogram present
✅ Idempotency working
```

**Warnings:**
- Metrics present but no values (expected for first run)
- No retry metrics found

### Final Verdict

**❌ DAY-1 FAIL**

**One-Line Reason:** Leader lock never acquired (`trader_is_leader = 0.0`), causing 187 kill-switch activations and `/ready` returning 503.

**Root Cause:** Redis client compatibility bug in `leader_lock.py` - `redis.get()` returns strings in newer Redis clients, but code expects bytes and calls `.decode()`.

---

## C) Issues & Risks (Ranked)

### 🔴 Critical (Blocks Day-1 PASS)

1. **Leader Lock Redis Compatibility Bug**
   - **Location:** `packages/core/leader_lock.py:52, 76, 101`
   - **Error:** `'str' object has no attribute 'decode'`
   - **Impact:** Leader lock never acquired → orchestrator paused → `/ready` = 503
   - **Evidence:** 187 `kill_switch_total{reason="leader_lock_lost"}` increments
   - **Root Cause:** Code assumes `redis.get()` returns bytes, but newer Redis clients return strings
   - **Fix:** Handle both bytes and strings (see Diffs section)

### 🟡 High (Blocks OCO Lifecycle)

2. **No OCO Lifecycle Proven**
   - **Evidence:** `trader_oco_children_created_total = 0.0`
   - **Impact:** Cannot verify OCO manager works end-to-end
   - **Likely Cause:** No orders placed (orchestrator paused due to leader lock)
   - **Fix:** Resolve leader lock first, then inject synthetic plan

3. **Database Connection Not Configured**
   - **Evidence:** `DATABASE_URL not set` in multiple checks
   - **Impact:** Cannot verify DB integrity (duplicates/orphans)
   - **Fix:** Set `DATABASE_URL` in `.env` or environment

### 🟢 Medium (Non-Blocking)

4. **Orchestrator Paused State**
   - **Evidence:** `"is_paused": true` in state endpoint
   - **Impact:** No new signals/orders during session
   - **Likely Cause:** Leader lock loss triggered pause
   - **Fix:** Auto-resume when leader lock re-acquired (already implemented)

5. **Metrics Not Populated**
   - **Evidence:** Paper E2E warnings about empty metrics
   - **Impact:** Cannot track signal/order generation
   - **Likely Cause:** No trading activity (paused)
   - **Fix:** Resolve leader lock, then metrics will populate

### 🔵 Low (Observational)

6. **2 Open Orders Found**
   - **Evidence:** `curl :8000/orders` returns 2
   - **Impact:** Minor - may be test artifacts
   - **Action:** Investigate if these are from previous sessions

---

## D) Actionable Improvements

### 24-Hour Fixes (Top 5)

#### 1. Fix Leader Lock Redis Compatibility ⚡ **CRITICAL**

**Rationale:** Blocks Day-1 PASS. System cannot acquire leader lock, causing continuous pause/resume cycles.

**Code Diff:**
```python
# packages/core/leader_lock.py

async def acquire(self) -> bool:
    try:
        result = await self.redis.set(
            self.key,
            self.instance_id,
            nx=True,
            ex=self.ttl
        )
        
        if result:
            self.is_leader = True
            logger.info("Leader lock acquired", instance_id=self.instance_id)
        else:
            existing_leader = await self.redis.get(self.key)
            # Fix: Handle both bytes and strings
            if existing_leader:
                if isinstance(existing_leader, bytes):
                    existing_leader = existing_leader.decode()
                logger.warning(
                    "Failed to acquire leader lock",
                    instance_id=self.instance_id,
                    existing_leader=existing_leader
                )
        
        return result
    except Exception as e:
        logger.error("Error acquiring leader lock", error=str(e))
        return False

async def refresh(self) -> bool:
    if not self.is_leader:
        return False
    
    try:
        pipe = self.redis.pipeline()
        pipe.watch(self.key)
        
        current_leader = await self.redis.get(self.key)
        # Fix: Handle both bytes and strings
        if current_leader:
            if isinstance(current_leader, bytes):
                current_leader = current_leader.decode()
        
        if current_leader is None or current_leader != self.instance_id:
            pipe.reset()
            self.is_leader = False
            logger.warning("Lost leader lock", instance_id=self.instance_id)
            return False
        
        # Still leader - refresh TTL
        pipe.multi()
        pipe.expire(self.key, self.ttl)
        await pipe.execute()
        
        return True
    except Exception as e:
        logger.error("Error refreshing leader lock", error=str(e))
        self.is_leader = False
        return False

async def release(self) -> None:
    if not self.is_leader:
        return
    
    try:
        current_leader = await self.redis.get(self.key)
        # Fix: Handle both bytes and strings
        if current_leader:
            if isinstance(current_leader, bytes):
                current_leader = current_leader.decode()
            
            if current_leader == self.instance_id:
                await self.redis.delete(self.key)
                logger.info("Leader lock released", instance_id=self.instance_id)
        self.is_leader = False
    except Exception as e:
        logger.error("Error releasing leader lock", error=str(e))
```

**Commands:**
```bash
# Apply fix
git checkout packages/core/leader_lock.py
# (apply diff above)

# Test
make start-paper
sleep 10
curl -s :8000/metrics | grep trader_is_leader  # Should be 1.0
curl -s :8000/ready | jq  # Should return 200
```

---

#### 2. Add DATABASE_URL Validation ⚡ **HIGH**

**Rationale:** DB checks skipped because `DATABASE_URL` not set. Need validation and fallback.

**Code Diff:**
```python
# scripts/score_day1.sh (add at top)

if [ -z "${DATABASE_URL:-}" ]; then
    echo "⚠️  DATABASE_URL not set - skipping DB checks"
    echo "   Set DATABASE_URL in .env or export before running"
    DB_AVAILABLE=0
else
    DB_AVAILABLE=1
fi

# Later in script:
if [ "$DB_AVAILABLE" -eq 1 ]; then
    # ... existing DB checks ...
else
    echo "⚠️  DB checks skipped (DATABASE_URL not set)"
    # Don't fail the test, but warn
fi
```

**Commands:**
```bash
# Set DATABASE_URL
export DATABASE_URL="postgresql+psycopg2://trader:trader@localhost:5432/aitrapp"

# Re-run scorer
make score-day1
```

---

#### 3. Add Leader Lock Health Check to Pre-Live Gate ⚡ **HIGH**

**Rationale:** Pre-live gate should catch leader lock issues before LIVE switch.

**Code Diff:**
```bash
# scripts/prelive_gate.sh (add after leader check)

# Enhanced leader lock check with retry
LEADER_RETRIES=3
LEADER_ACQUIRED=0
for i in $(seq 1 $LEADER_RETRIES); do
    leader=$(curl -s "$API/metrics" 2>/dev/null | awk -F' ' '/^trader_is_leader[^_]/ {print $2; exit}' || echo "0")
    if [[ "${leader:-0}" == "1" ]]; then
        LEADER_ACQUIRED=1
        break
    fi
    echo "   Retry $i/$LEADER_RETRIES: Leader lock not acquired, waiting 2s..."
    sleep 2
done

if [[ $LEADER_ACQUIRED -eq 0 ]]; then
    print_fail "Leader lock not acquired after $LEADER_RETRIES retries"
    PASS=0
fi
```

**Commands:**
```bash
# Test pre-live gate
make prelive-gate
```

---

#### 4. Add OCO Lifecycle Test to Paper E2E ⚡ **MEDIUM**

**Rationale:** Paper E2E should verify OCO manager creates children on entry fill.

**Code Diff:**
```python
# scripts/paper_e2e.py (add after order injection)

# Wait for OCO children to be created
print("Waiting for OCO children...")
for i in range(10):
    oco_children = get_metric("trader_oco_children_created_total")
    if oco_children and float(oco_children) > 0:
        print(f"✅ OCO children created: {oco_children}")
        break
    time.sleep(1)
else:
    print("⚠️  No OCO children created (may be expected if entry not filled)")
```

**Commands:**
```bash
# Re-run paper E2E
make paper-e2e
```

---

#### 5. Add Leader Lock Metrics to Dashboard ⚡ **MEDIUM**

**Rationale:** Operator needs visibility into leader lock state.

**Code Diff:**
```bash
# ops/live.sh (add to dashboard function)

watch -n 5 '
echo "=== Leader Lock ==="
curl -s :8000/metrics | grep trader_is_leader
echo ""
echo "=== Heartbeats ==="
curl -s :8000/metrics | grep -E "trader_(marketdata|order_stream|scan)_heartbeat_seconds"
echo ""
echo "=== Scan Supervisor ==="
curl -s :8000/debug/supervisor/status | jq
'
```

**Commands:**
```bash
# Test dashboard
make live-dashboard
```

---

### Week-1 Backlog (Top 10)

1. **Add Redis Connection Health Check** [SRE] [M]
   - Check Redis connectivity before starting orchestrator
   - Fail fast if Redis unavailable
   - Impact: Prevents silent leader lock failures

2. **Add OCO Lifecycle Metrics Dashboard** [DX] [S]
   - Track entry → SL/TP creation → fill → cancel
   - Visual timeline of OCO groups
   - Impact: Better debugging of OCO issues

3. **Add Database Connection Pooling** [Perf] [M]
   - Use SQLAlchemy connection pool
   - Monitor pool size and wait times
   - Impact: Better DB performance under load

4. **Add Synthetic Plan Injector to Paper E2E** [DX] [S]
   - Automatically inject test plan in E2E
   - Verify OCO lifecycle end-to-end
   - Impact: Automated OCO testing

5. **Add Leader Lock Acquisition Retry Logic** [SRE] [S]
   - Retry with exponential backoff on startup
   - Log retry attempts
   - Impact: More resilient startup

6. **Add Market Hours Validation to Pre-Live Gate** [Risk] [S]
   - Block LIVE switch outside market hours
   - Check for holidays
   - Impact: Prevents accidental LIVE switch

7. **Add Order Reconciliation Script** [SRE] [M]
   - Compare DB orders vs broker orders
   - Detect discrepancies
   - Impact: Better auditability

8. **Add Config Validation on Startup** [Risk] [S]
   - Validate risk limits, universe, strategies
   - Fail fast on invalid config
   - Impact: Prevents misconfiguration

9. **Add Prometheus Alert for Leader Lock Loss** [SRE] [S]
   - Alert when `trader_is_leader == 0` for >1m
   - Page operator
   - Impact: Faster incident response

10. **Add Database Backup Verification** [SRE] [M]
    - Verify backups are created daily
    - Test restore procedure
    - Impact: Better disaster recovery

---

## E) PR-Ready Diffs & Commands

### Fix 1: Leader Lock Redis Compatibility

**File:** `packages/core/leader_lock.py`

```diff
--- a/packages/core/leader_lock.py
+++ b/packages/core/leader_lock.py
@@ -45,7 +45,11 @@ class LeaderLock:
             else:
                 existing_leader = await self.redis.get(self.key)
-                logger.warning(
-                    "Failed to acquire leader lock",
-                    instance_id=self.instance_id,
-                    existing_leader=existing_leader.decode() if existing_leader else None
-                )
+                # Handle both bytes and strings (Redis client compatibility)
+                if existing_leader:
+                    if isinstance(existing_leader, bytes):
+                        existing_leader = existing_leader.decode()
+                logger.warning(
+                    "Failed to acquire leader lock",
+                    instance_id=self.instance_id,
+                    existing_leader=existing_leader
+                )
             
             return result
@@ -74,7 +78,11 @@ class LeaderLock:
             pipe.watch(self.key)
             
             current_leader = await self.redis.get(self.key)
-            if current_leader is None or current_leader.decode() != self.instance_id:
+            # Handle both bytes and strings (Redis client compatibility)
+            if current_leader:
+                if isinstance(current_leader, bytes):
+                    current_leader = current_leader.decode()
+            if current_leader is None or current_leader != self.instance_id:
                 pipe.reset()
                 self.is_leader = False
                 logger.warning("Lost leader lock", instance_id=self.instance_id)
@@ -99,7 +107,11 @@ class LeaderLock:
         try:
             # Only delete if we're still the leader
             current_leader = await self.redis.get(self.key)
-            if current_leader and current_leader.decode() == self.instance_id:
+            # Handle both bytes and strings (Redis client compatibility)
+            if current_leader:
+                if isinstance(current_leader, bytes):
+                    current_leader = current_leader.decode()
+            if current_leader and current_leader == self.instance_id:
                 await self.redis.delete(self.key)
                 logger.info("Leader lock released", instance_id=self.instance_id)
             self.is_leader = False
```

**Commands:**
```bash
# Apply fix
git apply leader_lock_fix.patch

# Test
make start-paper
sleep 10
curl -s :8000/metrics | grep trader_is_leader  # Should be 1.0
curl -s :8000/ready | jq  # Should return 200

# Re-run Day-1 scorer
make score-day1  # Should PASS after fix
```

---

### Fix 2: Add DATABASE_URL Validation

**File:** `scripts/score_day1.sh`

```diff
--- a/scripts/score_day1.sh
+++ b/scripts/score_day1.sh
@@ -6,6 +6,15 @@ API="${API:-http://localhost:8000}"
 DATABASE_URL="${DATABASE_URL:-postgresql+psycopg2://trader:trader@localhost:5432/aitrapp}"
 HEARTBEAT_MAX="${HEARTBEAT_MAX:-5}"
 
+# Check if DATABASE_URL is set and valid
+if [ -z "${DATABASE_URL:-}" ]; then
+    echo "⚠️  DATABASE_URL not set - DB checks will be skipped"
+    DB_AVAILABLE=0
+else
+    DB_AVAILABLE=1
+fi
+
 ok=1
 ...
 # 3. Check DB reconciliation
 echo "3️⃣  Checking DB for duplicates/orphans..."
-if command -v psql >/dev/null 2>&1 && [ -n "${DATABASE_URL:-}" ]; then
+if [ "$DB_AVAILABLE" -eq 1 ] && command -v psql >/dev/null 2>&1; then
     DB_CONN="${DATABASE_URL#postgresql+psycopg2://}"
     ...
 else
-    echo "⚠️  psql not found or DATABASE_URL not set. Skipping DB reconcile."
+    echo "⚠️  DB checks skipped (DATABASE_URL not set or psql not found)"
+    # Don't fail the test, but warn
 fi
```

**Commands:**
```bash
# Set DATABASE_URL
export DATABASE_URL="postgresql+psycopg2://trader:trader@localhost:5432/aitrapp"

# Re-run scorer
make score-day1
```

---

## Summary

**✅ What Works:**
- Scan supervisor running (1,088 ticks)
- All heartbeats < 5s
- Paper E2E test passes
- OCO manager, OrderWatcher, Risk gates implemented
- Persistence layer complete

**❌ What's Broken:**
- Leader lock never acquired (Redis compatibility bug)
- Orchestrator paused (due to leader lock loss)
- No OCO lifecycle proven (no orders placed)
- DB checks skipped (DATABASE_URL not set)

**🎯 Next Steps:**
1. Apply leader lock fix (24-hour fix #1)
2. Set DATABASE_URL and re-run scorer
3. Re-run Day-1 burn-in after fixes
4. Verify OCO lifecycle with synthetic plan injection

**Expected Outcome After Fixes:**
- Leader lock acquired → `/ready` = 200
- Orchestrator unpaused → signals/orders generated
- OCO lifecycle proven → `trader_oco_children_created_total > 0`
- Day-1 PASS ✅

---

**Report Generated:** 2025-11-13 20:10 IST  
**Next Review:** After applying 24-hour fixes

