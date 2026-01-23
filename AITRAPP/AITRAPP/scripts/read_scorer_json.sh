#!/usr/bin/env bash
# Hardened jq-less scorer JSON reader
# Selects latest JSON by mtime, validates keys, prints PASS/FAIL
set -euo pipefail

SCORER_DIR="${1:-reports/burnin}"
DAY_PREFIX="${2:-day2}"

# Find latest JSON by mtime (not filename)
LATEST_JSON=""
LATEST_MTIME=0

if [ ! -d "$SCORER_DIR" ]; then
    echo "FAIL: Directory not found: $SCORER_DIR"
    exit 1
fi

# Find file with latest mtime matching pattern
for json in "$SCORER_DIR"/${DAY_PREFIX}_*.json; do
    [ -f "$json" ] || continue
    MTIME=$(stat -f %m "$json" 2>/dev/null || stat -c %Y "$json" 2>/dev/null || echo "0")
    if [ "$MTIME" -gt "$LATEST_MTIME" ]; then
        LATEST_MTIME=$MTIME
        LATEST_JSON="$json"
    fi
done

if [ -z "$LATEST_JSON" ] || [ ! -f "$LATEST_JSON" ]; then
    echo "FAIL: No ${DAY_PREFIX} JSON found in $SCORER_DIR"
    exit 1
fi

# Check freshness (36h = 129600 seconds)
CURRENT_TIME=$(date +%s)
AGE=$((CURRENT_TIME - LATEST_MTIME))
MAX_AGE=129600  # 36 hours

if [ "$AGE" -gt "$MAX_AGE" ]; then
    echo "FAIL: JSON too old ($(($AGE / 3600))h, max 36h): $LATEST_JSON"
    exit 1
fi

# Extract values using awk/grep (jq-less)
STATUS=$(grep -o '"status"[[:space:]]*:[[:space:]]*"[^"]*"' "$LATEST_JSON" | awk -F'"' '{print $4}' || echo "UNKNOWN")
LEADER=$(grep -o '"leader"[[:space:]]*:[[:space:]]*[0-9.]*' "$LATEST_JSON" | awk '{print $NF}' || echo "0")
MD_HB=$(grep -A 3 '"heartbeats"' "$LATEST_JSON" | grep -o '"market"[[:space:]]*:[[:space:]]*[0-9.]*' | awk '{print $NF}' || echo "999")
ORDER_HB=$(grep -A 3 '"heartbeats"' "$LATEST_JSON" | grep -o '"orders"[[:space:]]*:[[:space:]]*[0-9.]*' | awk '{print $NF}' || echo "999")
SCAN_HB=$(grep -A 3 '"heartbeats"' "$LATEST_JSON" | grep -o '"scan"[[:space:]]*:[[:space:]]*[0-9.]*' | awk '{print $NF}' || echo "999")
LEADER_CHANGES=$(grep -o '"leader_changes"[[:space:]]*:[[:space:]]*[0-9.]*' "$LATEST_JSON" | awk '{print $NF}' || echo "999")
DUPLICATES=$(grep -o '"duplicates"[[:space:]]*:[[:space:]]*[0-9]*' "$LATEST_JSON" | awk '{print $NF}' || echo "999")
ORPHANS=$(grep -o '"orphans"[[:space:]]*:[[:space:]]*[0-9]*' "$LATEST_JSON" | awk '{print $NF}' || echo "999")
FLATTEN_MS=$(grep -o '"flatten_ms"[[:space:]]*:[[:space:]]*[0-9]*' "$LATEST_JSON" | awk '{print $NF}' || echo "9999")
CONFIG_SHA=$(grep -o '"config_sha"[[:space:]]*:[[:space:]]*"[^"]*"' "$LATEST_JSON" | awk -F'"' '{print $4}' || echo "unknown")
GIT_HEAD=$(grep -o '"git_head"[[:space:]]*:[[:space:]]*"[^"]*"' "$LATEST_JSON" | awk -F'"' '{print $4}' || echo "unknown")

# Validate completeness
if [[ "$STATUS" != "PASS" ]]; then
    echo "FAIL: status=$STATUS (expected PASS)"
    exit 1
fi

# Float comparison helper
float_lt() {
    awk "BEGIN{exit !($1 < $2)}"
}

float_le() {
    awk "BEGIN{exit !($1 <= $2)}"
}

# Validate all fields
if ! awk "BEGIN{exit !(${LEADER:-0} == 1)}"; then
    echo "FAIL: leader=$LEADER (expected 1)"
    exit 1
fi

if ! float_lt "$MD_HB" "5"; then
    echo "FAIL: hb_marketdata=$MD_HB (expected < 5)"
    exit 1
fi

if ! float_lt "$ORDER_HB" "5"; then
    echo "FAIL: hb_order_stream=$ORDER_HB (expected < 5)"
    exit 1
fi

if ! float_lt "$SCAN_HB" "5"; then
    echo "FAIL: hb_scan=$SCAN_HB (expected < 5)"
    exit 1
fi

if ! float_le "$LEADER_CHANGES" "2"; then
    echo "FAIL: leader_changes=$LEADER_CHANGES (expected <= 2)"
    exit 1
fi

if [ "$DUPLICATES" -ne 0 ]; then
    echo "FAIL: duplicates=$DUPLICATES (expected 0)"
    exit 1
fi

if [ "$ORPHANS" -ne 0 ]; then
    echo "FAIL: orphans=$ORPHANS (expected 0)"
    exit 1
fi

if [ "$FLATTEN_MS" -gt 2000 ]; then
    echo "FAIL: flatten_ms=$FLATTEN_MS (expected <= 2000)"
    exit 1
fi

# Check config_sha and git_head match runtime
RUNTIME_CONFIG_SHA=$(python -c "import hashlib; f=open('configs/app.yaml','rb'); print(hashlib.sha256(f.read()).hexdigest()[:16])" 2>/dev/null || echo "unknown")
RUNTIME_GIT_HEAD=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

if [[ "$CONFIG_SHA" != "$RUNTIME_CONFIG_SHA" ]]; then
    echo "FAIL: config_sha mismatch (JSON=$CONFIG_SHA, runtime=$RUNTIME_CONFIG_SHA)"
    exit 1
fi

if [[ "$GIT_HEAD" != "$RUNTIME_GIT_HEAD" ]]; then
    echo "FAIL: git_head mismatch (JSON=$GIT_HEAD, runtime=$RUNTIME_GIT_HEAD)"
    exit 1
fi

echo "PASS: $LATEST_JSON"
exit 0


