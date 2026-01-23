#!/usr/bin/env python3
"""
Check Zerodha authentication status and callback URL configuration.
"""
import os
from pathlib import Path

print("=" * 80)
print("ZERODHA AUTHENTICATION DIAGNOSTICS")
print("=" * 80)

# Check environment variables
env_file = Path("/Users/mac/dyad-apps/openalgo/.env")
if env_file.exists():
    print("\n1. Environment Configuration:")
    with open(env_file, 'r') as f:
        for line in f:
            if 'BROKER_API_KEY' in line or 'BROKER_API_SECRET' in line or 'REDIRECT_URL' in line:
                # Mask sensitive values
                if 'SECRET' in line:
                    parts = line.split('=')
                    if len(parts) > 1:
                        secret = parts[1].strip()
                        masked = secret[:4] + '*' * (len(secret) - 8) + secret[-4:] if len(secret) > 8 else '***'
                        print(f"   {parts[0].strip()} = {masked}")
                else:
                    print(f"   {line.strip()}")
else:
    print("\n⚠️  .env file not found")

# Check redirect URL
redirect_url = os.getenv('REDIRECT_URL', 'Not set')
print(f"\n2. Callback URL: {redirect_url}")

# Expected format
print("\n3. Expected Callback Flow:")
print("   a) User clicks 'Connect Broker' on OpenAlgo")
print("   b) Redirected to: https://kite.trade/connect/login?api_key=YOUR_API_KEY")
print("   c) User logs in to Zerodha")
print("   d) Zerodha redirects to: http://127.0.0.1:5001/zerodha/callback?request_token=XXX&status=success")
print("   e) OpenAlgo exchanges request_token for access_token")

print("\n4. Common Issues:")
print("   ⚠️  If stuck at login page:")
print("      - Make sure you're logged into OpenAlgo first (session required)")
print("      - Check that callback URL matches in Zerodha Kite Connect app settings")
print("      - Verify REDIRECT_URL in .env matches: http://127.0.0.1:5001/zerodha/callback")
print("      - Try clearing browser cache/cookies")
print("      - Check if server is running on port 5001")

print("\n5. Manual Steps to Complete Authentication:")
print("   a) Go to: http://127.0.0.1:5001/auth/login")
print("   b) Login to OpenAlgo")
print("   c) Go to: http://127.0.0.1:5001/auth/broker")
print("   d) Select 'Zerodha' and click 'Connect Broker'")
print("   e) Complete login on Zerodha page")
print("   f) You'll be redirected back to OpenAlgo")

print("\n" + "=" * 80)
