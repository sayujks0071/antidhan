#!/usr/bin/env bash
# Day-2 PASS Scorer (includes leader flaps check)
set -euo pipefail

# Enforce timezone consistently
export TZ="${TZ:-Asia/Kolkata}"

API="${API:-http://localhost:8000}"
DATABASE_URL="${DATABASE_URL:-postgresql+psycopg2://trader:trader@localhost:5432/aitrapp}"
HEARTBEAT_MAX="${HEARTBEAT_MAX:-5}"
LEADER_FLAPS_MAX="${LEADER_FLAPS_MAX:-2}"  # Max leader changes in session

ok=1

echo "📊 Day-2 PASS Scorer"
echo "===================="
echo ""

# 1. Check /ready endpoint
echo "1️⃣  Checking /ready endpoint..."
if curl -sf "$API/ready" >/dev/null; then
    echo "   ✅ /ready returns 200"
else
    echo "   ❌ /ready returns 503 (Not Ready)"
    ok=0
fi
echo ""

# 2. Check heartbeats
echo "2️⃣  Checking heartbeats (< ${HEARTBEAT_MAX}s)..."
MD_HB=$(curl -s "$API/metrics" 2>/dev/null | awk '/^trader_marketdata_heartbeat_seconds[^_]/ {print $2; exit}' || echo "999")
ORDER_HB=$(curl -s "$API/metrics" 2>/dev/null | awk '/^trader_order_stream_heartbeat_seconds[^_]/ {print $2; exit}' || echo "999")
SCAN_HB=$(curl -s "$API/metrics" 2>/dev/null | awk '/^trader_scan_heartbeat_seconds[^_]/ {print $2; exit}' || echo "999")

BAD_HB=0
curl -s "$API/metrics" 2>/dev/null | awk -v max="$HEARTBEAT_MAX" '/^trader_(marketdata|order_stream|scan)_heartbeat_seconds[^_]/ {
    if ($2 >= max) {
        print "   ❌ " $1 " = " $2 "s (stale)"
        bad=1
    } else {
        print "   ✅ " $1 " = " $2 "s"
    }
} END { exit bad }' || BAD_HB=1

if [ "$BAD_HB" -eq 1 ]; then
    ok=0
fi
echo ""

# 3. Check leader lock
echo "3️⃣  Checking leader lock..."
LEADER=$(curl -s "$API/metrics" 2>/dev/null | awk '/^trader_is_leader[^_]/ {print $2; exit}' || echo "0")
# Handle both "1" and "1.0" (float comparison)
if awk "BEGIN{exit !(${LEADER:-0} == 1)}"; then
    echo "   ✅ trader_is_leader = ${LEADER}"
else
    echo "   ❌ trader_is_leader = $LEADER (expected 1)"
    ok=0
fi
echo ""

# 4. Check leader flaps (Day-2 specific)
echo "4️⃣  Checking leader flaps (< ${LEADER_FLAPS_MAX} changes)..."
LEADER_CHANGES=$(curl -s "$API/metrics" 2>/dev/null | awk '/^trader_leader_changes_total/ {print $2; exit}' || echo "0")
LEADER_CHANGES_INT=${LEADER_CHANGES%.*}

if [ "$LEADER_CHANGES_INT" -le "$LEADER_FLAPS_MAX" ]; then
    echo "   ✅ trader_leader_changes_total = ${LEADER_CHANGES} (≤ ${LEADER_FLAPS_MAX})"
else
    echo "   ❌ trader_leader_changes_total = ${LEADER_CHANGES} (> ${LEADER_FLAPS_MAX})"
    ok=0
fi
echo ""

# 5. Check DB reconciliation
echo "5️⃣  Checking database integrity..."
if command -v psql >/dev/null 2>&1 && [ -n "${DATABASE_URL:-}" ]; then
    DB_CONN="${DATABASE_URL#postgresql+psycopg2://}"
    RECONCILE_OUTPUT=$(psql "$DB_CONN" -tAc "\i scripts/reconcile_db.sql" 2>/dev/null)
    DUPS=$(echo "$RECONCILE_OUTPUT" | grep 'duplicates' | awk '{print $NF}' || echo "0")
    ORPHANS=$(echo "$RECONCILE_OUTPUT" | grep 'orphans' | awk '{print $NF}' || echo "0")
    
    if [[ "$DUPS" -eq 0 ]] && [[ "$ORPHANS" -eq 0 ]]; then
        echo "   ✅ DB Reconcile: 0 duplicates, 0 orphans"
    else
        echo "   ❌ DB Reconcile: Found ${DUPS} duplicates, ${ORPHANS} orphans"
        echo "$RECONCILE_OUTPUT"
        ok=0
    fi
else
    echo "   ⚠️  psql not found or DATABASE_URL not set. Skipping DB reconcile."
    # Not failing the test if psql is not available, but warning
fi
echo ""

# Calculate config_sha and git_head
CONFIG_SHA=$(python -c "import hashlib; f=open('configs/app.yaml','rb'); print(hashlib.sha256(f.read()).hexdigest()[:16])" 2>/dev/null || echo "unknown")
GIT_HEAD=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
FLATTEN_MS=$(curl -s "$API/metrics" 2>/dev/null | awk '/^trader_flatten_duration_ms/ {print $2; exit}' || echo "0")
FLATTEN_MS=${FLATTEN_MS%.*}

# Get duplicates/orphans count
DUPLICATES=0
ORPHANS=0
if command -v psql >/dev/null 2>&1 && [ -n "${DATABASE_URL:-}" ]; then
    DB_CONN="${DATABASE_URL#postgresql+psycopg2://}"
    DUPLICATES=$(psql "$DB_CONN" -tAc "
        SELECT COUNT(*) 
        FROM (
            SELECT client_order_id
            FROM orders
            WHERE client_order_id IS NOT NULL
            GROUP BY client_order_id
            HAVING COUNT(*) > 1
        ) dupes;
    " 2>/dev/null || echo "0")
    ORPHANS=$(psql "$DB_CONN" -tAc "
        SELECT COUNT(*)
        FROM orders o
        WHERE o.tag IN ('STOP', 'TP1', 'TP2')
          AND o.parent_group IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 
              FROM orders parent 
              WHERE parent.parent_group = o.parent_group 
                AND parent.tag = 'ENTRY'
          );
    " 2>/dev/null || echo "0")
fi

# Output JSON summary with completeness fields
mkdir -p reports/burnin
TIMESTAMP=$(date -Is)
JSON_OUTPUT=$(jq -n \
  --arg status "$( [[ $ok -eq 1 ]] && echo "PASS" || echo "FAIL" )" \
  --arg leader "${LEADER:-0}" \
  --arg md_hb "$MD_HB" \
  --arg order_hb "$ORDER_HB" \
  --arg scan_hb "$SCAN_HB" \
  --arg leader_changes "${LEADER_CHANGES:-0}" \
  --arg config_sha "$CONFIG_SHA" \
  --arg git_head "$GIT_HEAD" \
  --arg flatten_ms "${FLATTEN_MS:-0}" \
  --arg duplicates "${DUPLICATES:-0}" \
  --arg orphans "${ORPHANS:-0}" \
  --arg timestamp "$TIMESTAMP" \
  '{
    status: $status,
    timestamp: $timestamp,
    config_sha: $config_sha,
    git_head: $git_head,
    leader: ($leader | tonumber),
    heartbeats: {
      market: ($md_hb | tonumber),
      orders: ($order_hb | tonumber),
      scan: ($scan_hb | tonumber)
    },
    leader_changes: ($leader_changes | tonumber),
    flatten_ms: ($flatten_ms | tonumber),
    duplicates: ($duplicates | tonumber),
    orphans: ($orphans | tonumber)
  }')

# Atomic write: temp file + atomic move (avoid partial reads)
mkdir -p reports/burnin
TODAY=$(date +%F)
OUT="reports/burnin/day2_${TODAY}.json"
TMP="$(mktemp "reports/burnin/.day2_${TODAY}.json.XXXX" 2>/dev/null || echo "reports/burnin/.day2_${TODAY}.json.tmp")"
printf "%s" "$JSON_OUTPUT" > "${TMP}"
# fsync to reduce risk of power loss/partial write
if command -v sync >/dev/null 2>&1; then sync; fi
mv -f "${TMP}" "${OUT}"
echo "wrote ${OUT}"
echo ""

echo "=================================="
if [[ $ok -eq 1 ]]; then
    echo "✅ DAY-2 PASS"
    echo ""
    echo "All checks passed:"
    echo "  - /ready = 200"
    echo "  - All heartbeats < ${HEARTBEAT_MAX}s"
    echo "  - Leader lock = 1"
    echo "  - Leader changes ≤ ${LEADER_FLAPS_MAX}"
    echo "  - No duplicates/orphans"
    exit 0
else
    echo "❌ DAY-2 FAIL"
    echo ""
    echo "Some checks failed. Review output above."
    exit 1
fi

