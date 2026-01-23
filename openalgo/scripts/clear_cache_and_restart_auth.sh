#!/bin/bash
# Clear OpenAlgo session data and restart authentication flow

echo "=========================================="
echo "Clearing Cache and Restarting Auth Flow"
echo "=========================================="

cd /Users/mac/dyad-apps/openalgo

# Clear Flask session files if any
echo "1. Clearing server-side session data..."
find . -name "*.session" -type f -delete 2>/dev/null
find . -name "flask_session" -type d -exec rm -rf {} + 2>/dev/null
echo "   ✅ Server session data cleared"

# Restart server to clear in-memory sessions
echo ""
echo "2. Restarting OpenAlgo server to clear sessions..."
PIDS=$(lsof -ti:5001 2>/dev/null)

if [ -z "$PIDS" ]; then
    echo "   ⚠️  No server running on port 5001"
else
    for PID in $PIDS; do
        echo "   Stopping PID: $PID"
        kill $PID 2>/dev/null
        sleep 1
        if kill -0 $PID 2>/dev/null; then
            kill -9 $PID 2>/dev/null
        fi
    done
    echo "   ✅ Server stopped"
    sleep 2
fi

echo ""
echo "3. Starting server..."
cd /Users/mac/dyad-apps/openalgo
source venv/bin/activate
FLASK_PORT=5001 nohup python app.py > /dev/null 2>&1 &
sleep 3

# Check if server started
if curl -s http://127.0.0.1:5001/auth/login > /dev/null 2>&1; then
    echo "   ✅ Server started successfully"
else
    echo "   ⚠️  Server may still be starting..."
fi

echo ""
echo "=========================================="
echo "NEXT STEPS:"
echo "=========================================="
echo "1. Clear your browser cache and cookies:"
echo "   - Chrome/Edge: Ctrl+Shift+Delete (Windows) or Cmd+Shift+Delete (Mac)"
echo "   - Firefox: Ctrl+Shift+Delete (Windows) or Cmd+Shift+Delete (Mac)"
echo "   - Safari: Cmd+Option+E (Mac)"
echo ""
echo "2. Or use Incognito/Private mode:"
echo "   - Chrome: Ctrl+Shift+N (Windows) or Cmd+Shift+N (Mac)"
echo "   - Firefox: Ctrl+Shift+P (Windows) or Cmd+Shift+P (Mac)"
echo "   - Safari: Cmd+Shift+N (Mac)"
echo ""
echo "3. Start fresh authentication:"
echo "   a) Go to: http://127.0.0.1:5001/auth/login"
echo "   b) Login to OpenAlgo"
echo "   c) Go to: http://127.0.0.1:5001/auth/broker"
echo "   d) Select 'Zerodha' and click 'Connect Broker'"
echo "   e) Complete Zerodha login"
echo ""
echo "=========================================="
