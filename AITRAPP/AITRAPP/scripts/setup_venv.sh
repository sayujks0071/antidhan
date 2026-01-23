#!/usr/bin/env bash
# Clean virtual environment setup
set -euo pipefail

echo "🔧 Setting up clean virtual environment"
echo "========================================"
echo ""

# Check if venv already exists
if [ -d "venv" ]; then
    echo "⚠️  Virtual environment already exists"
    read -p "Remove and recreate? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "   → Removing existing venv..."
        rm -rf venv
    else
        echo "   → Using existing venv"
        echo ""
        echo "✅ To activate: source venv/bin/activate"
        exit 0
    fi
fi

# Create venv
echo "1️⃣  Creating virtual environment..."
python3 -m venv venv
echo "   ✅ Virtual environment created"
echo ""

# Activate and upgrade pip
echo "2️⃣  Upgrading pip, setuptools, wheel..."
source venv/bin/activate
python -m pip install -U pip setuptools wheel
echo "   ✅ Base packages upgraded"
echo ""

# Install dependencies
echo "3️⃣  Installing dependencies..."
pip install -r requirements.txt
echo "   ✅ Dependencies installed"
echo ""

# Quick sanity check
echo "4️⃣  Running sanity check..."
if python -c "import fastapi, uvicorn; print('✅ deps_ok')" 2>/dev/null; then
    echo "   ✅ Core dependencies verified"
else
    echo "   ❌ Dependency check failed"
    exit 1
fi
echo ""

echo "✅ Virtual environment setup complete!"
echo ""
echo "📋 Next steps:"
echo "   1. Activate venv: source venv/bin/activate"
echo "   2. Start PAPER: make start-paper"
echo "   3. Or manual: PORT=8000 make paper"
echo ""
echo "💡 Tip: Add 'source venv/bin/activate' to your shell profile for auto-activation"

