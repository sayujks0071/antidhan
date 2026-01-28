#!/bin/bash
# Quick Backup Script for OpenAlgo Settings
# Creates a timestamped backup of strategy configurations and environment variables

cd "$(dirname "$0")"

echo "Creating backup..."
python3 scripts/save_settings.py

exit $?
