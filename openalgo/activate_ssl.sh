#!/bin/bash
# SSL Certificate Configuration Helper for OpenAlgo
# This script sets up SSL_CERT_FILE environment variable for Python SSL verification

# Activate virtual environment
source venv/bin/activate

# Set SSL certificate file path
export SSL_CERT_FILE=$(python3 -m certifi)

echo "✓ SSL certificates configured: $SSL_CERT_FILE"
echo "✓ Virtual environment activated"
echo ""
echo "You can now run: python3 app.py"
