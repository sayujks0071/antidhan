#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

# Ensure we fail on any error
set -o pipefail

# ---- Day-2 JSON PASS gate (jq-less hardened) --------------------------------
# Blocks LIVE if latest Day-2 scorer JSON is missing, stale (>36h, IST), or FAIL.
# Tries jq first; falls back to POSIX awk/grep parser if jq is absent.

TZ="${TZ:-Asia/Kolkata}"
export TZ
HEARTBEAT_MAX="${HEARTBEAT_MAX:-5}"
FLAP_MAX="${FLAP_MAX:-2}"
FRESH_WINDOW_SECS=$((36*3600))   # 36h

now_epoch() {
  date +%s
}

# Cross-platform file mtime -> epoch (GNU/BSD stat)
file_mtime_epoch() {
  local f="$1"
  if stat -f %m "$f" >/dev/null 2>&1; then
    stat -f %m "$f"
  else
    stat -c %Y "$f"
  fi
}

latest_day2_json() {
  # Choose newest Day-2 JSON by mtime; quiet if none
  ls -t reports/burnin/day2_*.json 2>/dev/null | head -n1 || true
}

have_jq() { command -v jq >/dev/null 2>&1; }

# Lenient JSON key extractor (numbers/strings) for our own scorer format
json_get_key_fallback() {
  # Usage: json_get_key_fallback <file> <key>
  # Returns raw value (unquoted for numbers, unquoted string if present).
  local f="$1" k="$2"
  # try number first
  awk -v key="\"${k}\"" '
    BEGIN{FS=":"}
    $0 ~ key {
      # join the rest of the line after first colon
      sub(/.*:[[:space:]]*/, "", $0);
      # strip trailing commas/braces/spaces
      gsub(/[[:space:]]*,?[[:space:]]*$/, "", $0);
      gsub(/[[:space:]]*[,}][[:space:]]*$/, "", $0);
      # strip quotes if any
      gsub(/^"[[:space:]]*/,"",$0); gsub(/[[:space:]]*"$/,"",$0);
      print $0; exit
    }
  ' "$f"
}

read_day2_json_values() {
  # Echo k=v lines for required fields; empty if missing
  local f="$1"
  if have_jq; then
    # Try jq fast path
    jq -r '
      [
        "status=" + ( .status // "" ),
        "leader=" + ( (.leader|tostring) // "" ),
        "hb_marketdata=" + ( (.heartbeats.market|tostring) // "" ),
        "hb_order_stream=" + ( (.heartbeats.orders|tostring) // "" ),
        "hb_scan=" + ( (.heartbeats.scan|tostring) // "" ),
        "leader_changes=" + ( (.leader_changes|tostring) // "" ),
        "duplicates=" + ( (.duplicates|tostring) // "" ),
        "orphans=" + ( (.orphans|tostring) // "" ),
        "flatten_ms=" + ( (.flatten_ms|tostring) // "" ),
        "config_sha=" + ( .config_sha // "" ),
        "git_head=" + ( .git_head // "" )
      ] | .[]
    ' "$f" 2>/dev/null || true
  else
    # Fallback parser (robust enough for our generated JSON)
    for key in status leader hb_marketdata hb_order_stream hb_scan leader_changes duplicates orphans flatten_ms config_sha git_head; do
      val="$(json_get_key_fallback "$f" "$key" | tr -d '\r')"
      echo "${key}=${val}"
    done
  fi
}

gate_day2_json_pass() {
  local f
  f="$(latest_day2_json)"
  if [[ -z "${f:-}" || ! -f "$f" ]]; then
    echo "FAIL: Day-2 scorer JSON not found (reports/burnin/day2_*.json)."
    exit 1
  fi

  # Freshness check (<=36h)
  local now mt age
  now="$(now_epoch)"
  mt="$(file_mtime_epoch "$f")"
  age=$(( now - mt ))
  if (( age > FRESH_WINDOW_SECS )); then
    echo "FAIL: Day-2 JSON stale (age=${age}s > ${FRESH_WINDOW_SECS}s): $f"
    exit 1
  fi

  # Extract values
  declare -A kv=()
  while IFS='=' read -r k v; do
    [[ -n "${k:-}" ]] && kv["$k"]="${v:-}"
  done < <(read_day2_json_values "$f")

  # Required fields & validations
  local status="${kv[status]:-}"
  local leader="${kv[leader]:-}"
  local hb_m="${kv[hb_marketdata]:-}"
  local hb_o="${kv[hb_order_stream]:-}"
  local hb_s="${kv[hb_scan]:-}"
  local flaps="${kv[leader_changes]:-}"
  local dups="${kv[duplicates]:-}"
  local orph="${kv[orphans]:-}"
  local flat_ms="${kv[flatten_ms]:-}"

  # Hard checks (fail closed)
  [[ "${status}" == "PASS" ]] || { echo "FAIL: Day-2 JSON status=${status} (expected PASS). File: $f"; exit 1; }
  [[ "${leader}" == "1" ]] || { echo "FAIL: leader==${leader} (expected 1). File: $f"; exit 1; }

  awk -v m="${hb_m:-9999}" -v o="${hb_o:-9999}" -v s="${hb_s:-9999}" -v mx="${HEARTBEAT_MAX}" '
    BEGIN{
      if (m>=mx || o>=mx || s>=mx) { exit 1 } else { exit 0 }
    }' || { echo "FAIL: heartbeats >= ${HEARTBEAT_MAX}s (m=${hb_m} o=${hb_o} s=${hb_s}). File: $f"; exit 1; }

  awk -v fl="${flaps:-9999}" 'BEGIN{ exit (fl<=2 ? 0 : 1) }' || { echo "FAIL: leader_changes=${flaps} (>2). File: $f"; exit 1; }
  awk -v d="${dups:-9999}" 'BEGIN{ exit (d==0 ? 0 : 1) }' || { echo "FAIL: duplicates=${dups} (!=0). File: $f"; exit 1; }
  awk -v r="${orph:-9999}" 'BEGIN{ exit (r==0 ? 0 : 1) }' || { echo "FAIL: orphans=${orph} (!=0). File: $f"; exit 1; }
  awk -v fm="${flat_ms:-999999}" 'BEGIN{ exit (fm<=2000 ? 0 : 1) }' || { echo "FAIL: flatten_ms=${flat_ms}ms (>2000ms). File: $f"; exit 1; }

  echo "PASS: Day-2 scorer JSON ok → ${f}"
}

# ------------------------------------------------------------------------------

API="${API:-http://localhost:8000}"
ACK_P95_MS_MAX="${ACK_P95_MS_MAX:-500}"
LEADER_REQUIRED="${LEADER_REQUIRED:-1}"

fail() { 
    echo "❌ PRELIVE GATE FAIL: $1" >&2
    exit 1
}

pass() {
    echo "✅ $1"
}

# Extract metrics
leader=$(curl -s "$API/metrics" 2>/dev/null | awk -F' ' '/^trader_is_leader[^_]/ {print $2; exit}' || echo "0")
mkt=$(curl -s "$API/metrics" 2>/dev/null | awk -F' ' '/^trader_marketdata_heartbeat_seconds[^_]/ {print $2; exit}' || echo "999")
ord=$(curl -s "$API/metrics" 2>/dev/null | awk -F' ' '/^trader_order_stream_heartbeat_seconds[^_]/ {print $2; exit}' || echo "999")

# Dry flatten test
if command -v gdate >/dev/null 2>&1; then
    t0=$(gdate +%s%3N)
    t1_cmd="gdate +%s%3N"
else
    t0=$(python3 -c "import time; print(int(time.time() * 1000))" 2>/dev/null || echo "$(date +%s)000")
    t1_cmd='python3 -c "import time; print(int(time.time() * 1000))"'
fi

curl -s -X POST "$API/flatten" -H "Content-Type: application/json" -d '{"reason":"prelive_gate"}' >/dev/null || fail "Flatten endpoint failed"
sleep 2
open=$(curl -s "$API/positions" 2>/dev/null | jq -r '.count // . | length' 2>/dev/null || echo "0")
t1=$(eval "$t1_cmd" 2>/dev/null || echo "$(date +%s)000")
flat_ms=$((t1 - t0))

# Check open orders
open_orders=$(curl -s "$API/orders" 2>/dev/null | jq -r '. | length' 2>/dev/null || echo "0")

# Validate checks
PASS=1
[[ "${leader:-0}" == "$LEADER_REQUIRED" ]] || PASS=0
awk "BEGIN{exit !(${mkt:-999} < $HEARTBEAT_MAX && ${ord:-999} < $HEARTBEAT_MAX)}" || PASS=0
[[ "$open" -eq 0 ]] || PASS=0
[[ $flat_ms -le 2000 ]] || PASS=0
[[ "$open_orders" -eq 0 ]] || PASS=0

# 6) Scan heartbeat must be fresh
echo "Checking scan heartbeat..."
SCAN=$(curl -s "$API/metrics" 2>/dev/null | awk '/^trader_scan_heartbeat_seconds[^_]/ {print $2; exit}' || echo "999")
if awk "BEGIN{exit !(${SCAN:-999} < $HEARTBEAT_MAX)}"; then
    pass "Scan heartbeat OK (${SCAN}s, max=${HEARTBEAT_MAX}s)"
else
    PASS=0
    echo "❌ PRELIVE GATE FAIL: Stale scan heartbeat (${SCAN}s, max=${HEARTBEAT_MAX}s)" >&2
fi
    
# === New: Require Day-2 scorer PASS (fresh) before LIVE consideration ===
# This runs before other LIVE gates to prevent stale/old PASS from slipping.
if [[ "${PRELIVE_REQUIRE_DAY2_JSON:-1}" -eq 1 ]]; then
  echo "== Gate: Day-2 scorer JSON PASS (fresh, ≤36h) =="
  gate_day2_json_pass || fail "Day-2 scorer JSON gate failed"
  pass "Day-2 scorer JSON: PASS (validated with completeness checks)"
fi

# 8) Schema gate: details column exists and action is enum type
echo "Checking audit_logs schema..."
if command -v psql >/dev/null 2>&1 && [ -n "${DATABASE_URL:-}" ]; then
    DB_CONN="${DATABASE_URL#postgresql+psycopg2://}"
    SCHEMA_OK=$(psql "$DB_CONN" -tAc "
        SELECT (SELECT COUNT(*) FROM information_schema.columns 
                WHERE table_name='audit_logs' AND column_name='details')=1
           AND (SELECT typname FROM pg_type 
                WHERE oid=(SELECT atttypid FROM pg_attribute 
                           WHERE attrelid='audit_logs'::regclass AND attname='action'))='auditactionenum';
    " 2>/dev/null | grep -qx 't' && echo 't' || echo 'f')
    
    if [[ "$SCHEMA_OK" == "t" ]]; then
        pass "audit_logs schema aligned (details column + enum action)"
    else
        PASS=0
        fail "audit_logs schema not aligned (details/enum check failed)"
    fi
else
    echo "⚠️  Schema check skipped (psql not available or DATABASE_URL not set)"
fi

       # --- SEBI 2025 compliance gate additions ---
       : "${EXPECTED_EGRESS_IP:=}"
       : "${TOPS_CAP_PER_SEC:=8}"
       : "${MODE_PROFILE:=PERSONAL}"
       : "${EXCHANGE_ALGO_ID:=}"
       
       # 1) Static IP check
       if [[ -n "${EXPECTED_EGRESS_IP}" ]]; then
         CURR_IP="$(curl -s --max-time 2 https://api.ipify.org || true)"
         if [[ -z "${CURR_IP}" || "${CURR_IP}" != "${EXPECTED_EGRESS_IP}" ]]; then
           fail "egress_ip" "Egress IP mismatch or unavailable (curr='${CURR_IP}', expected='${EXPECTED_EGRESS_IP}')"
         else
           pass "egress_ip" "OK (${CURR_IP})"
         fi
       else
         fail "egress_ip" "EXPECTED_EGRESS_IP not set"
       fi
       
       # 2) TOPS cap
       if [[ "${TOPS_CAP_PER_SEC}" -ge 10 ]]; then
         fail "tops_cap" "TOPS >= 10/s requires registered algo; set <10 or register"
       else
         pass "tops_cap" "cap=${TOPS_CAP_PER_SEC}/s"
       fi
       
       # 3) Algo-ID presence (placeholder; becomes mandatory when broker field goes live)
       if [[ -z "${EXCHANGE_ALGO_ID}" ]]; then
         fail "exchange_algo_id" "EXCHANGE_ALGO_ID missing (set placeholder now; map to broker field when live)"
       else
         pass "exchange_algo_id" "present"
       fi
       
       # 4) Family-only (PERSONAL profile)
       if [[ "${MODE_PROFILE^^}" == "PERSONAL" ]]; then
         if [[ -z "${WHITELISTED_CLIENTS}" ]]; then
           fail "family_only" "WHITELISTED_CLIENTS empty"
         else
           pass "family_only" "whitelist set"
         fi
       else
         pass "family_only" "PROVIDER mode"
       fi
       
       # Output JSON summary
       jq -n \
         --arg leader "${leader:-0}" \
         --arg mkt "${mkt:-999}" \
         --arg ord "${ord:-999}" \
         --argjson flat_ms "$flat_ms" \
         --argjson positions_open "$open" \
         --argjson orders_open "$open_orders" \
         --arg status "$( [[ $PASS -eq 1 ]] && echo "PASS" || echo "FAIL" )" \
         '{
           status: $status,
           leader: ($leader | tonumber),
           heartbeats: {
             market: ($mkt | tonumber),
             orders: ($ord | tonumber),
             scan: ($SCAN | tonumber)
           },
           flatten_ms: $flat_ms,
           positions_open: $positions_open,
           orders_open: $orders_open
         }'
       
       # Human-readable output
       if [[ $PASS -eq 1 ]]; then
           echo ""
           echo "✅ PRELIVE GATE PASS - System ready for LIVE switch"
           exit 0
       else
           echo ""
           # Explicit gate: fail immediately if leader == 0 (prevents Redis compatibility regression)
           [[ "${leader:-0}" == "$LEADER_REQUIRED" ]] || fail "Leader lock not held (trader_is_leader=${leader:-0}, expected $LEADER_REQUIRED) - Redis compatibility regression?"
           awk "BEGIN{exit !(${mkt:-999} < $HEARTBEAT_MAX && ${ord:-999} < $HEARTBEAT_MAX)}" || fail "Stale heartbeats (marketdata=${mkt}s, order_stream=${ord}s, max=${HEARTBEAT_MAX}s)"
           [[ "$open" -eq 0 ]] || fail "Positions not flat after flatten (count=$open)"
           [[ $flat_ms -le 2000 ]] || fail "Flatten exceeded 2s: ${flat_ms}ms"
           [[ "$open_orders" -eq 0 ]] || fail "Found $open_orders open orders"
           exit 1
       fi
