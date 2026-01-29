#!/bin/bash
# Restart OpenAlgo server to clear rate limits
# Rate limits are stored in memory and reset on server restart

echo "=========================================="
echo "Clearing Rate Limits by Restarting Server"
echo "=========================================="

cd /Users/mac/dyad-apps/openalgo

# Find and stop server processes on port 5001
echo "1. Stopping server on port 5001..."
PIDS=$(lsof -ti:5001 2>/dev/null)

if [ -z "$PIDS" ]; then
    echo "   ⚠️  No server running on port 5001"
else
    for PID in $PIDS; do
        echo "   Stopping PID: $PID"
        kill $PID 2>/dev/null
        sleep 1
        # Force kill if still running
        if kill -0 $PID 2>/dev/null; then
            echo "   Force killing PID: $PID"
            kill -9 $PID 2>/dev/null
        fi
    done
    echo "   ✅ Server stopped"
    sleep 2
fi

echo ""
echo "2. Rate limits are now cleared (stored in memory)"
echo ""
echo "3. To restart the server, run:"
echo "   cd /Users/mac/dyad-apps/openalgo"
echo "   source venv/bin/activate"
echo "   FLASK_PORT=5001 python app.py"
echo ""
echo "Or if you have a startup script, use that instead."
echo ""
echo "=========================================="
echo "Rate Limit Info:"
echo "- 5 login attempts per minute"
echo "- 25 login attempts per hour"
echo "- Limits reset on server restart"
echo "=========================================="
