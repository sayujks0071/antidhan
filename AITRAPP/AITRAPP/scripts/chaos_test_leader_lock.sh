#!/usr/bin/env bash
# Chaos test for leader lock self-healing
# Simulates Redis hiccup / lock loss and verifies auto-reacquire

set -euo pipefail

API="${API:-http://localhost:8000}"
REDIS_CONTAINER="${REDIS_CONTAINER:-redis}"
REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}"
HEARTBEAT_MAX="${HEARTBEAT_MAX:-5}"
WAIT_READY_TIMEOUT="${WAIT_READY_TIMEOUT:-90}"
NONINTERACTIVE="${NONINTERACTIVE:-0}"
PAUSE_ON_FAIL="${PAUSE_ON_FAIL:-0}"

# Helper functions
jqval() { curl -s "$API/$1" 2>/dev/null | jq -r "$2" 2>/dev/null || echo ""; }
metric() { curl -s "$API/metrics" 2>/dev/null | awk -v k="^$1" '$0 ~ k {print $2; exit}' || echo "0"; }

wait_ready() {
  echo "⏳ Waiting for /ready..."
  local t=0
  while ! curl -sf "$API/ready" >/dev/null 2>&1; do
    sleep 2
    t=$((t+2))
    if (( t > WAIT_READY_TIMEOUT )); then
      echo "❌ Not ready after ${WAIT_READY_TIMEOUT}s"
      return 1
    fi
  done
  echo "✅ Ready"
}

assert_paused() {
  local paused
  paused=$(jqval state '.paused' 2>/dev/null || echo "unknown")
  if [[ "$paused" != "true" ]]; then
    echo "❌ Expected paused=true, got $paused"
    if [[ "$PAUSE_ON_FAIL" == "1" ]]; then
      echo "🚨 Pausing on failure..."
      make abort 2>/dev/null || true
    fi
    exit 1
  fi
  echo "✅ Orchestrator paused"
}

assert_resumed() {
  local paused
  paused=$(jqval state '.paused' 2>/dev/null || echo "unknown")
  if [[ "$paused" != "false" ]]; then
    echo "❌ Expected paused=false, got $paused"
    if [[ "$PAUSE_ON_FAIL" == "1" ]]; then
      echo "🚨 Pausing on failure..."
      make abort 2>/dev/null || true
    fi
    exit 1
  fi
  echo "✅ Orchestrator resumed"
}

snapshot_metrics() {
  echo "— Metrics Snapshot —"
  curl -s "$API/metrics" 2>/dev/null | grep -E '^trader_(is_leader|scan_supervisor_state|scan_heartbeat_seconds|order_stream_heartbeat_seconds|marketdata_heartbeat_seconds|kill_switch_total)' | sort || echo "   (metrics unavailable)"
  echo ""
}

echo "🧪 Leader Lock Chaos Test"
echo "========================="
echo ""

# Check if Docker is available
DOCKER_AVAILABLE=false
if command -v docker >/dev/null 2>&1; then
    DOCKER_AVAILABLE=true
fi

# Check if Redis is running in Docker
REDIS_IN_DOCKER=false
if [ "$DOCKER_AVAILABLE" = true ]; then
    if docker ps 2>/dev/null | grep -q "$REDIS_CONTAINER"; then
        REDIS_IN_DOCKER=true
    fi
fi

# Check if Redis is running locally
REDIS_LOCAL=false
if redis-cli -u "$REDIS_URL" ping >/dev/null 2>&1; then
    REDIS_LOCAL=true
fi

if [ "$REDIS_IN_DOCKER" = false ] && [ "$REDIS_LOCAL" = false ]; then
    echo "⚠️  Redis not found (neither in Docker nor locally)"
    echo "   Please ensure Redis is running before running this test"
    exit 1
fi

if [ "$REDIS_IN_DOCKER" = false ] && [ "$REDIS_LOCAL" = true ]; then
    echo "ℹ️  Redis is running locally (not in Docker)"
    echo "   This test will provide manual steps for testing"
    echo ""
fi

# Create reports directory
mkdir -p reports/chaos

echo "1️⃣  Baseline check (leader should be 1)..."
LEADER_BEFORE=$(metric trader_is_leader)
READY_BEFORE=$(jqval ready '.status' || echo "not_ready")
echo "   Leader: $LEADER_BEFORE"
echo "   Ready: $READY_BEFORE"
echo ""

if [[ "$LEADER_BEFORE" != "1" ]]; then
    echo "⚠️  Warning: Leader is not 1 at baseline (may indicate existing issues)"
fi

snapshot_metrics

echo "2️⃣  Stopping Redis (simulating hiccup)..."
if [ "$REDIS_IN_DOCKER" = true ]; then
    docker compose stop "$REDIS_CONTAINER" 2>/dev/null || docker stop "$REDIS_CONTAINER" 2>/dev/null || true
    echo "   ✅ Redis stopped (Docker)"
elif [ "$REDIS_LOCAL" = true ]; then
    echo "   ⚠️  Redis is running locally"
    echo "   📋 MANUAL STEP: Stop Redis manually:"
    echo "      - If using brew: brew services stop redis"
    echo "      - If using systemd: sudo systemctl stop redis"
    echo "      - Or kill the process: pkill redis-server"
    echo ""
    if [[ "$NONINTERACTIVE" == "0" ]]; then
        read -p "   Press Enter after you've stopped Redis..."
    else
        echo "   (NONINTERACTIVE: assuming Redis is stopped)"
        sleep 2
    fi
fi
echo ""

echo "3️⃣  Waiting 5 seconds for lock to expire..."
sleep 5
echo ""

echo "4️⃣  Verifying degraded state (leader lost, paused, /ready 503)..."
snapshot_metrics

# Check /ready should fail
if curl -sf "$API/ready" >/dev/null 2>&1; then
    echo "❌ /ready should be 503 (not ready)"
    if [[ "$PAUSE_ON_FAIL" == "1" ]]; then
        make abort 2>/dev/null || true
    fi
    exit 1
fi
echo "   ✅ /ready correctly returns 503"

# Check leader should be 0
LEADER_AFTER_STOP=$(metric trader_is_leader)
if [[ "$LEADER_AFTER_STOP" != "0" ]]; then
    echo "❌ trader_is_leader should be 0, got $LEADER_AFTER_STOP"
    if [[ "$PAUSE_ON_FAIL" == "1" ]]; then
        make abort 2>/dev/null || true
    fi
    exit 1
fi
echo "   ✅ trader_is_leader = 0"

# Check orchestrator is paused
assert_paused

echo ""
echo "✅ Leader lost → API stays up, trading paused"
echo ""

echo "5️⃣  Verifying API is still up (should be healthy)..."
HEALTH=$(jqval health '.status' || echo "unknown")
echo "   Health: $HEALTH"
if [[ "$HEALTH" == "healthy" ]]; then
    echo "   ✅ API still running (good - no crash)"
else
    echo "   ⚠️  API health: $HEALTH"
fi
echo ""

echo "6️⃣  Restarting Redis to recover..."
if [ "$REDIS_IN_DOCKER" = true ]; then
    docker compose start "$REDIS_CONTAINER" 2>/dev/null || docker start "$REDIS_CONTAINER" 2>/dev/null || true
    echo "   ✅ Redis restarted (Docker)"
elif [ "$REDIS_LOCAL" = true ]; then
    echo "   ⚠️  Redis is running locally"
    echo "   📋 MANUAL STEP: Start Redis manually:"
    echo "      - If using brew: brew services start redis"
    echo "      - If using systemd: sudo systemctl start redis"
    echo "      - Or start manually: redis-server"
    echo ""
    if [[ "$NONINTERACTIVE" == "0" ]]; then
        read -p "   Press Enter after you've started Redis..."
    else
        echo "   (NONINTERACTIVE: assuming Redis is started)"
        sleep 2
    fi
fi
echo ""

echo "7️⃣  Waiting for auto-reacquire and recovery..."
wait_ready || {
    echo "❌ System did not become ready within timeout"
    if [[ "$PAUSE_ON_FAIL" == "1" ]]; then
        make abort 2>/dev/null || true
    fi
    exit 1
}

echo ""
echo "8️⃣  Verifying recovered state (leader re-acquired, resumed, /ready 200)..."
snapshot_metrics

# Check leader should be 1
LEADER_AFTER_RESTART=$(metric trader_is_leader)
if [[ "$LEADER_AFTER_RESTART" != "1" ]]; then
    echo "❌ trader_is_leader should be 1, got $LEADER_AFTER_RESTART"
    if [[ "$PAUSE_ON_FAIL" == "1" ]]; then
        make abort 2>/dev/null || true
    fi
    exit 1
fi
echo "   ✅ trader_is_leader = 1"

# Check orchestrator is resumed
assert_resumed

# Check /ready should be 200
READY_AFTER_RESTART=$(jqval ready '.status' || echo "not_ready")
if [[ "$READY_AFTER_RESTART" != "ready" ]]; then
    echo "❌ /ready should be 'ready', got $READY_AFTER_RESTART"
    if [[ "$PAUSE_ON_FAIL" == "1" ]]; then
        make abort 2>/dev/null || true
    fi
    exit 1
fi
echo "   ✅ /ready = 200"

# Check heartbeats
SCAN_HB=$(metric trader_scan_heartbeat_seconds)
ORDER_HB=$(metric trader_order_stream_heartbeat_seconds)
MD_HB=$(metric trader_marketdata_heartbeat_seconds)

if awk "BEGIN{exit !($SCAN_HB < $HEARTBEAT_MAX)}"; then
    echo "   ✅ Scan heartbeat: ${SCAN_HB}s (< ${HEARTBEAT_MAX}s)"
else
    echo "   ⚠️  Scan heartbeat: ${SCAN_HB}s (expected < ${HEARTBEAT_MAX}s)"
fi

if awk "BEGIN{exit !($ORDER_HB < $HEARTBEAT_MAX)}"; then
    echo "   ✅ Order stream heartbeat: ${ORDER_HB}s (< ${HEARTBEAT_MAX}s)"
else
    echo "   ⚠️  Order stream heartbeat: ${ORDER_HB}s (expected < ${HEARTBEAT_MAX}s)"
fi

if awk "BEGIN{exit !($MD_HB < $HEARTBEAT_MAX)}"; then
    echo "   ✅ Market data heartbeat: ${MD_HB}s (< ${HEARTBEAT_MAX}s)"
else
    echo "   ⚠️  Market data heartbeat: ${MD_HB}s (expected < ${HEARTBEAT_MAX}s)"
fi

echo ""
echo "✅ Leader re-acquired → /ready 200 → trading resumed"
echo ""

echo "📊 Test Summary:"
echo "================"
echo "   Before:      Leader=$LEADER_BEFORE, Ready=$READY_BEFORE"
echo "   After stop:  Leader=$LEADER_AFTER_STOP, Ready=503"
echo "   After restart: Leader=$LEADER_AFTER_RESTART, Ready=$READY_AFTER_RESTART"
echo ""

# Record evidence
TS=$(date -Is 2>/dev/null || date +"%Y-%m-%dT%H:%M:%S")
LOG_FILE="reports/chaos/leader_lock_${TS//:/-}.log"
{
    echo "leader_lock_chaos_test,$TS"
    echo "leader_before,$LEADER_BEFORE"
    echo "leader_after_stop,$LEADER_AFTER_STOP"
    echo "leader_after_recovery,$LEADER_AFTER_RESTART"
    echo "ready_before,$READY_BEFORE"
    echo "ready_after_recovery,$READY_AFTER_RESTART"
    echo "scan_hb,$SCAN_HB"
    echo "order_hb,$ORDER_HB"
    echo "md_hb,$MD_HB"
    echo "health,$HEALTH"
} | tee "$LOG_FILE"
echo "📝 Wrote $LOG_FILE"
echo ""

# Final verdict
if [[ "$LEADER_AFTER_STOP" == "0" ]] && \
   [[ "$HEALTH" == "healthy" ]] && \
   [[ "$LEADER_AFTER_RESTART" == "1" ]] && \
   [[ "$READY_AFTER_RESTART" == "ready" ]]; then
    echo "✅ CHAOS TEST PASSED"
    echo "   - Leader lock lost correctly"
    echo "   - API stayed up (no crash)"
    echo "   - Leader lock re-acquired automatically"
    echo "   - Orchestrator paused and resumed correctly"
    echo "   - /ready flipped 503 → 200"
    exit 0
else
    echo "⚠️  CHAOS TEST INCOMPLETE"
    echo "   - Some checks didn't pass as expected"
    echo "   - Review the output above"
    if [[ "$PAUSE_ON_FAIL" == "1" ]]; then
        echo "🚨 Pausing on failure..."
        make abort 2>/dev/null || true
    fi
    exit 1
fi
