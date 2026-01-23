#!/bin/bash
# Immediate abort macro - pause, flatten, switch to PAPER

set -e

echo "🚨 ABORTING - Pausing, flattening, switching to PAPER..."

# Pause
echo "1. Pausing..."
curl -s -X POST localhost:8000/pause | jq

# Flatten
echo "2. Flattening all positions..."
curl -s -X POST localhost:8000/flatten \
    -H "Content-Type: application/json" \
    -d '{"reason":"abort"}' | jq

# Switch to PAPER
echo "3. Switching to PAPER..."
curl -s -X POST localhost:8000/mode \
    -H "Content-Type: application/json" \
    -d '{"mode":"PAPER"}' | jq

echo "✅ Abort complete"

