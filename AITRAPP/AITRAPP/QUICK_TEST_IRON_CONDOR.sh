#!/bin/bash
# Quick script to test Iron Condor on NIFTY historical data

echo "🧪 Iron Condor Backtest Setup"
echo "=============================="
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install -q -r requirements.txt

# Check if data files exist
if [ ! -f "docs/NSE OPINONS DATA/OPTIDX_NIFTY_CE_12-Aug-2025_TO_12-Nov-2025.csv" ]; then
    echo "❌ Error: Historical data files not found!"
    echo "   Expected location: docs/NSE OPINONS DATA/"
    exit 1
fi

echo "✅ Setup complete!"
echo ""
echo "🚀 Running Iron Condor backtest..."
echo ""

# Run the test
python scripts/test_iron_condor.py

# Deactivate virtual environment
deactivate

echo ""
echo "✅ Test complete!"

