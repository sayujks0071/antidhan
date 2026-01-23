#!/usr/bin/env bash
# Self-test the pre-live gate with synthetic cases (no jq required)
set -euo pipefail
IFS=$'\n\t'

export TZ="${TZ:-Asia/Kolkata}"
mkdir -p reports/burnin

# Backup existing JSON files if any
BACKUP_DIR="reports/burnin/.test_backup_$(date +%s)"
mkdir -p "$BACKUP_DIR"
mv reports/burnin/day*.json "$BACKUP_DIR/" 2>/dev/null || true

cleanup() {
    # Restore backup
    mv "$BACKUP_DIR"/*.json reports/burnin/ 2>/dev/null || true
    rm -rf "$BACKUP_DIR"
}
trap cleanup EXIT

# 1) Valid JSON → PASS
cat > reports/burnin/day2_0000-01-01.json <<'JSON'
{
  "status":"PASS",
  "leader":1,
  "heartbeats": {
    "market":0.9,
    "orders":1.1,
    "scan":2.0
  },
  "leader_changes":0,
  "duplicates":0,
  "orphans":0,
  "flatten_ms":900,
  "config_sha":"abc123",
  "git_head":"deadbeef"
}
JSON
python3 - <<'PY'
import os, time
p="reports/burnin/day2_0000-01-01.json"
# Make it look "fresh" (now - 60s)
os.utime(p,(time.time()-60, time.time()-60))
PY
echo "Case A (valid): expect PASS"
if bash scripts/prelive_gate.sh >/dev/null 2>&1; then
    echo "✅ PASS (expected)"
else
    echo "❌ Unexpected FAIL"
    exit 1
fi

# 2) Stale (>36h) → FAIL
python3 - <<'PY'
import os, time
p="reports/burnin/day2_0000-01-01.json"
os.utime(p,(time.time()-60*60*37, time.time()-60*60*37))
PY
echo "Case B (stale): expect FAIL"
if bash scripts/prelive_gate.sh >/dev/null 2>&1; then
    echo "❌ Unexpected PASS"
    exit 1
else
    echo "✅ FAIL (expected)"
fi

# 3) Bad fields → FAIL
cat > reports/burnin/day2_0000-01-02.json <<'JSON'
{"status":"FAIL","leader":0,"heartbeats":{"market":10,"orders":10,"scan":10},"leader_changes":99,"duplicates":1,"orphans":1,"flatten_ms":9999}
JSON
python3 - <<'PY'
import os, time
p="reports/burnin/day2_0000-01-02.json"
os.utime(p,(time.time()-60, time.time()-60))
PY
echo "Case C (bad fields): expect FAIL"
if bash scripts/prelive_gate.sh >/dev/null 2>&1; then
    echo "❌ Unexpected PASS"
    exit 1
else
    echo "✅ FAIL (expected)"
fi

echo ""
echo "✅ All gate tests behaved as expected."


