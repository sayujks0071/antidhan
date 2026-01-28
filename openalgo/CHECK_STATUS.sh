#!/bin/bash
# OpenAlgo Status Check Script

echo "=========================================="
echo "   OpenAlgo Status Check"
echo "=========================================="
echo ""

# Configuration files
echo "📁 Configuration Files:"
echo "  .env: $(test -f .env && echo '✅ EXISTS' || echo '❌ MISSING')"
echo "  Database: $(test -f db/openalgo.db && echo '✅ EXISTS ($(du -h db/openalgo.db | cut -f1))' || echo '❌ MISSING')"
echo "  Strategy env: $(test -f strategies/strategy_env.json && echo '✅ EXISTS' || echo '❌ MISSING')"
echo ""

# Server status
echo "🖥️  Server Status:"
if lsof -i :5001 >/dev/null 2>&1; then
    echo "  Port 5001: ✅ RUNNING"
    echo "  URL: http://127.0.0.1:5001"
    
    # Test API
    RESPONSE=$(curl -s http://127.0.0.1:5001/api/v1/ping 2>&1)
    if echo "$RESPONSE" | grep -q "status\|ok"; then
        echo "  API: ✅ RESPONDING"
    else
        echo "  API: ⚠️  Not responding correctly"
    fi
else
    echo "  Port 5001: ❌ NOT RUNNING"
    echo ""
    echo "  To start server:"
    echo "    cd /Users/mac/dyad-apps/probable-fiesta/openalgo"
    echo "    source /Users/mac/dyad-apps/openalgo/venv/bin/activate"
    echo "    bash start.sh"
fi
echo ""

# Authentication check
echo "🔐 Authentication:"
if [ -f db/openalgo.db ]; then
    AUTH_COUNT=$(sqlite3 db/openalgo.db "SELECT COUNT(*) FROM auth WHERE broker='zerodha';" 2>/dev/null || echo "0")
    if [ "$AUTH_COUNT" -gt 0 ]; then
        echo "  Zerodha auth: ✅ Found in database"
        echo "  (Run health check to verify token validity)"
    else
        echo "  Zerodha auth: ⚠️  Not found - need to authenticate"
    fi
else
    echo "  Database not accessible"
fi
echo ""

# Virtual environment
echo "🐍 Python Environment:"
if [ -d "/Users/mac/dyad-apps/openalgo/venv" ]; then
    echo "  Virtual env: ✅ Found at /Users/mac/dyad-apps/openalgo/venv"
else
    echo "  Virtual env: ⚠️  Not found"
fi
echo ""

# Quick links
echo "🔗 Quick Links:"
echo "  Dashboard: http://127.0.0.1:5001/dashboard"
echo "  Strategies: http://127.0.0.1:5001/python"
echo "  Broker Auth: http://127.0.0.1:5001/auth/broker"
echo "  Health Check: python3 scripts/authentication_health_check.py"
echo ""
