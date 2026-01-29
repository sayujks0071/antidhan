#!/bin/bash
# Start OpenAlgo on Port 5001 for Kite (temporarily override .env)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENALGO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=================================================================================="
echo "  STARTING OPENALGO ON PORT 5001 (KITE)"
echo "=================================================================================="
echo ""

cd "$OPENALGO_DIR"

# Backup .env if it exists
if [ -f ".env" ]; then
    BACKUP=".env.backup.$(date +%s)"
    cp .env "$BACKUP"
    echo "✅ Backed up .env to $BACKUP"
fi

# Temporarily modify .env to use port 5001
if [ -f ".env" ]; then
    # Replace FLASK_PORT line
    sed -i.bak "s/^FLASK_PORT.*/FLASK_PORT = '5001'/" .env
    echo "✅ Updated .env to use port 5001"
fi

# Start server
echo ""
echo "🚀 Starting OpenAlgo on port 5001..."
echo "   Web UI: http://127.0.0.1:5001"
echo "   Press Ctrl+C to stop"
echo ""

python3 app.py
