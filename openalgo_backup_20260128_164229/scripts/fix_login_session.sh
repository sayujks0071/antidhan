#!/bin/bash
# Fix login session issues by clearing rate limits and restarting server

echo "=================================================================================="
echo "  FIXING LOGIN SESSION ISSUE"
echo "=================================================================================="
echo ""

# Step 1: Stop current server
echo "1. Stopping current OpenAlgo server..."
pkill -f "python.*app.py" 2>/dev/null
sleep 2
echo "   ✅ Server stopped"
echo ""

# Step 2: Clear browser cookies/session (instructions)
echo "2. Clear browser session:"
echo "   - Open browser DevTools (F12)"
echo "   - Go to Application/Storage tab"
echo "   - Clear Cookies for http://127.0.0.1:5001"
echo "   - Or use incognito/private window"
echo ""

# Step 3: Wait for rate limit to clear
echo "3. Waiting 60 seconds for rate limit to clear..."
for i in {60..1}; do
    echo -ne "   ⏳ $i seconds remaining...\r"
    sleep 1
done
echo -e "\n   ✅ Rate limit should be cleared"
echo ""

# Step 4: Restart server
echo "4. Restarting server on port 5001..."
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
./scripts/start_port5001_kite.sh > /tmp/openalgo_5001_fixed.log 2>&1 &
SERVER_PID=$!
echo "   Server PID: $SERVER_PID"
sleep 8

# Step 5: Verify server
echo ""
echo "5. Verifying server..."
if curl -s http://127.0.0.1:5001/api/v1/ping > /dev/null 2>&1; then
    echo "   ✅ Server is running"
else
    echo "   ⚠️  Server may still be starting..."
fi

echo ""
echo "=================================================================================="
echo "  NEXT STEPS"
echo "=================================================================================="
echo ""
echo "1. Open browser in INCOGNITO/PRIVATE mode"
echo "2. Navigate to: http://127.0.0.1:5001/auth/login"
echo "3. Login with:"
echo "   Username: sayujks0071"
echo "   Password: Apollo@20417"
echo "4. You should be redirected to broker page"
echo ""
