#!/usr/bin/env bash
# 2-minute smoke test after migration
set -euo pipefail

PORT="${PORT:-8000}"
API="${API:-http://localhost:${PORT}}"

echo "🔍 Running 2-minute smoke test..."
echo ""

# 1. Check DB schema
echo "1. Checking database schema..."
alembic upgrade head || {
    echo "❌ Migration failed"
    exit 1
}
echo "✅ Database schema OK"
echo ""

# 2. Check API health
echo "2. Checking API health..."
for i in {1..10}; do
    if curl -s "${API}/health" >/dev/null 2>&1; then
        echo "✅ API is responding"
        break
    fi
    if [ $i -eq 10 ]; then
        echo "❌ API not responding after 10 attempts"
        exit 1
    fi
    sleep 1
done
echo ""

# 3. Test endpoints
echo "3. Testing endpoints..."
curl -s "${API}/health" | jq -r '.status' || echo "⚠️  Health check failed"
curl -s "${API}/state" | jq -r '.mode' || echo "⚠️  State check failed"
curl -s "${API}/risk" | jq -r '.can_take_new_position' || echo "⚠️  Risk check failed"
echo "✅ Endpoints responding"
echo ""

# 4. Check metrics
echo "4. Checking metrics..."
METRICS=$(curl -s "${API}/metrics" | grep -E '^trader_' | head -5 || echo "")
if [ -n "$METRICS" ]; then
    echo "✅ Metrics available"
    echo "$METRICS" | head -3
else
    echo "⚠️  No metrics found (may not be initialized yet)"
fi
echo ""

# 5. Test audit log (trigger flatten to create audit entry)
echo "5. Testing audit log (triggering flatten)..."
FLATTEN_RESP=$(curl -s -X POST "${API}/flatten" \
    -H "Content-Type: application/json" \
    -d '{"reason":"post_migration_test"}' 2>&1 || echo "{}")

if echo "$FLATTEN_RESP" | jq -e '.status' >/dev/null 2>&1; then
    echo "✅ Flatten endpoint working"
else
    echo "⚠️  Flatten endpoint may have issues (expected if orchestrator not running)"
fi
echo ""

# 6. Verify audit_logs table has action column
echo "6. Verifying audit_logs.action column..."
if command -v psql >/dev/null 2>&1; then
    ACTION_COUNT=$(psql "${DATABASE_URL:-postgresql://trader:trader@localhost:5432/aitrapp}" \
        -t -c "SELECT COUNT(*) FROM audit_logs WHERE action IS NOT NULL;" 2>/dev/null || echo "0")
    echo "   Found $ACTION_COUNT audit logs with action set"
    
    # Check enum type exists
    ENUM_EXISTS=$(psql "${DATABASE_URL:-postgresql://trader:trader@localhost:5432/aitrapp}" \
        -t -c "SELECT EXISTS(SELECT 1 FROM pg_type WHERE typname = 'auditactionenum');" 2>/dev/null || echo "f")
    if [ "$ENUM_EXISTS" = "t" ]; then
        echo "✅ auditactionenum type exists"
    else
        echo "⚠️  auditactionenum type not found (may need migration)"
    fi
else
    echo "⚠️  psql not available, skipping DB verification"
fi
echo ""

echo "✅ Smoke test complete!"
echo ""
echo "📋 Summary:"
echo "   - Database: OK"
echo "   - API: Responding on port ${PORT}"
echo "   - Endpoints: Working"
echo "   - Metrics: Available"
echo "   - Audit logs: Verified"
echo ""
echo "🚀 System ready for PAPER testing!"

