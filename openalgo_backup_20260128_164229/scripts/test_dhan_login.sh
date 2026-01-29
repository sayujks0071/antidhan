#!/bin/bash
# Test Dhan Login Configuration
# Usage: ./test_dhan_login.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENALGO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=================================================================================="
echo "  TESTING DHAN LOGIN CONFIGURATION"
echo "=================================================================================="
echo ""

# Check if port 5002 is running
if ! curl -s http://127.0.0.1:5002/api/v1/ping > /dev/null 2>&1; then
    echo "❌ Port 5002 is not accessible!"
    echo "   Start it first: ./scripts/start_dhan_port5002_noenv.sh"
    exit 1
fi

echo "✅ Port 5002 is accessible"
echo ""

# Check BROKER_API_KEY format
echo "📋 Checking BROKER_API_KEY configuration..."
BROKER_KEY=$(ps e -p $(lsof -ti:5002) 2>/dev/null | grep BROKER_API_KEY | head -1 | sed 's/.*BROKER_API_KEY=//' | cut -d' ' -f1)

if [ -z "$BROKER_KEY" ]; then
    echo "⚠️  BROKER_API_KEY not found in process environment"
    echo "   Expected format: client_id:::api_key"
    echo "   Current: Not set"
else
    if [[ "$BROKER_KEY" == *":::"* ]]; then
        CLIENT_ID=$(echo "$BROKER_KEY" | cut -d':' -f1)
        API_KEY=$(echo "$BROKER_KEY" | cut -d':' -f4-)
        echo "✅ Format correct:"
        echo "   Client ID: $CLIENT_ID"
        echo "   API Key: ${API_KEY:0:10}..."
    else
        echo "⚠️  Format issue:"
        echo "   Current: $BROKER_KEY"
        echo "   Expected: client_id:::api_key"
    fi
fi

echo ""
echo "📋 Testing Dhan OAuth endpoints..."

# Test initiate-oauth endpoint (will redirect if not logged in)
echo "1. Testing /dhan/initiate-oauth..."
RESPONSE=$(curl -s -L http://127.0.0.1:5002/dhan/initiate-oauth 2>&1)
if echo "$RESPONSE" | grep -q "login\|Login\|redirect"; then
    echo "   ⚠️  Redirecting to login (need to login to OpenAlgo first)"
elif echo "$RESPONSE" | grep -q "Dhan\|dhan\|oauth"; then
    echo "   ✅ Endpoint responding"
else
    echo "   Response: ${RESPONSE:0:100}..."
fi

echo ""
echo "=================================================================================="
echo "  TROUBLESHOOTING STEPS"
echo "=================================================================================="
echo ""
echo "1. ✅ Login to OpenAlgo Web UI first:"
echo "   http://127.0.0.1:5002"
echo "   Username: sayujks0071"
echo "   Password: Apollo@20417"
echo ""
echo "2. ✅ Then go to Broker Login → Dhan"
echo ""
echo "3. ✅ Check BROKER_API_KEY is set correctly:"
echo "   Format: client_id:::api_key"
echo "   Expected: 1105009139:::df1da5de"
echo ""
echo "4. ✅ Verify redirect URL matches:"
echo "   http://127.0.0.1:5002/dhan/callback"
echo ""
