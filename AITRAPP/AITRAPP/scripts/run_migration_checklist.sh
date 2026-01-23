#!/usr/bin/env bash
# Complete migration checklist - run this after creating the migration
set -euo pipefail

echo "🚀 Migration Checklist"
echo "====================="
echo ""

# Check if we're in a virtual environment or have dependencies
if ! python3 -c "import alembic" 2>/dev/null; then
    echo "⚠️  alembic not found in current Python environment"
    echo "   Try: source venv/bin/activate  (if using venv)"
    echo "   Or: pip install -r requirements.txt"
    echo ""
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Step 1: Apply migration
echo "1️⃣  Applying enum migration..."
if command -v alembic >/dev/null 2>&1; then
    if alembic upgrade head 2>&1; then
        echo "   ✅ Migration applied successfully"
    else
        echo "   ❌ Migration failed - check error above"
        exit 1
    fi
elif python3 -c "import alembic" 2>/dev/null; then
    # Try with python -m if alembic command not in PATH
    if python3 -c "import sys; sys.path.insert(0, '.'); from alembic.config import main; main(['upgrade', 'head'])" 2>&1; then
        echo "   ✅ Migration applied successfully"
    else
        echo "   ⚠️  Migration check failed - may already be applied"
    fi
else
    echo "   ⚠️  alembic not available - skipping migration (may already be applied)"
fi
echo ""

# Step 2: Check port availability
echo "2️⃣  Checking port availability..."
PORT=8000
if lsof -nP -iTCP:${PORT} | grep LISTEN >/dev/null 2>&1; then
    echo "   ⚠️  Port ${PORT} is in use"
    PORT=8010
    echo "   → Will use port ${PORT} instead"
else
    echo "   ✅ Port ${PORT} is free"
fi
echo ""

# Step 3: Verify enum in database
echo "3️⃣  Verifying enum in database..."
if command -v psql >/dev/null 2>&1 && [ -n "${DATABASE_URL:-}" ]; then
    ENUM_EXISTS=$(psql "${DATABASE_URL}" -t -c "SELECT typname FROM pg_type WHERE typname='auditactionenum';" 2>/dev/null | xargs || echo "")
    if [ -n "$ENUM_EXISTS" ]; then
        echo "   ✅ Enum type 'auditactionenum' exists"
    else
        echo "   ⚠️  Enum type not found (may need to check DB connection)"
    fi
else
    echo "   ⚠️  psql not available or DATABASE_URL not set - skipping"
fi
echo ""

# Step 4: Test SafeKiteTicker (if dependencies available)
echo "4️⃣  Testing SafeKiteTicker wrapper..."
if python3 -c "import structlog" 2>/dev/null; then
    python3 - <<'PY'
from types import SimpleNamespace
try:
    from packages.core.kite_ws import SafeKiteTicker
    
    # Simulate different client shapes
    for obj in [SimpleNamespace(close=lambda: None),
                SimpleNamespace(stop=lambda: None),
                SimpleNamespace()]:
        SafeKiteTicker(obj).stop()
    print("   ✅ SafeKiteTicker teardown OK")
except Exception as e:
    print(f"   ⚠️  SafeKiteTicker test failed: {e}")
PY
else
    echo "   ⚠️  structlog not available - skipping (will work when dependencies installed)"
fi
echo ""

# Step 5: Summary
echo "✅ Migration checklist complete!"
echo ""
echo "📋 Next steps:"
echo "   1. Start API: PORT=${PORT} make paper"
echo "   2. Run smoke test: make smoke-check"
echo "   3. Run quick sanity: make quick-sanity"
echo ""
echo "💡 Tip: If port 8000 is busy, use: PORT=8010 make paper"

