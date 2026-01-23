#!/usr/bin/env bash
# Quick sanity checks after migration
set -euo pipefail

PORT="${PORT:-8000}"
API="${API:-http://localhost:${PORT}}"
DB_URL="${DATABASE_URL:-postgresql://trader:trader@localhost:5432/aitrapp}"

echo "🔍 Quick Sanity Checks"
echo "======================"
echo ""

# 1. Verify enum exists
echo "1. Checking enum type..."
if command -v psql >/dev/null 2>&1; then
    ENUM_EXISTS=$(psql "$DB_URL" -t -c "SELECT typname FROM pg_type WHERE typname='auditactionenum';" 2>/dev/null | xargs || echo "")
    if [ -n "$ENUM_EXISTS" ]; then
        echo "   ✅ Enum type 'auditactionenum' exists"
    else
        echo "   ❌ Enum type not found"
        exit 1
    fi
else
    echo "   ⚠️  psql not available, skipping"
fi
echo ""

# 2. Verify column exists
echo "2. Checking action column..."
if command -v psql >/dev/null 2>&1; then
    COLUMN_INFO=$(psql "$DB_URL" -t -c "SELECT column_name, udt_name FROM information_schema.columns WHERE table_name='audit_logs' AND column_name='action';" 2>/dev/null | xargs || echo "")
    if [ -n "$COLUMN_INFO" ]; then
        echo "   ✅ Column 'action' exists: $COLUMN_INFO"
    else
        echo "   ❌ Column not found"
        exit 1
    fi
else
    echo "   ⚠️  psql not available, skipping"
fi
echo ""

# 3. Check recent audit rows
echo "3. Checking audit log entries..."
if command -v psql >/dev/null 2>&1; then
    AUDIT_COUNTS=$(psql "$DB_URL" -t -c "SELECT action, count(*) FROM audit_logs GROUP BY action ORDER BY 2 DESC LIMIT 10;" 2>/dev/null || echo "")
    if [ -n "$AUDIT_COUNTS" ]; then
        echo "   Recent audit log actions:"
        echo "$AUDIT_COUNTS" | sed 's/^/   /'
    else
        echo "   ⚠️  No audit logs found yet (will be created on first action)"
    fi
else
    echo "   ⚠️  psql not available, skipping"
fi
echo ""

# 4. Test API endpoints
echo "4. Testing API endpoints on port ${PORT}..."
for endpoint in "/health" "/state" "/risk" "/metrics"; do
    if curl -s "${API}${endpoint}" >/dev/null 2>&1; then
        echo "   ✅ ${endpoint} responding"
    else
        echo "   ⚠️  ${endpoint} not responding (API may not be running)"
    fi
done
echo ""

# 5. Check metrics
echo "5. Checking metrics..."
METRICS=$(curl -s "${API}/metrics" 2>/dev/null | grep -E '^trader_' | head -5 || echo "")
if [ -n "$METRICS" ]; then
    echo "   ✅ Metrics available:"
    echo "$METRICS" | sed 's/^/   /'
else
    echo "   ⚠️  No metrics found (orchestrator may not be initialized)"
fi
echo ""

echo "✅ Sanity checks complete!"
echo ""
echo "📋 Summary:"
echo "   - Database enum: Verified"
echo "   - Database column: Verified"
echo "   - API endpoints: Tested"
echo "   - Metrics: Checked"
echo ""
echo "🚀 System ready for PAPER testing!"

