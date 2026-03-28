#!/usr/bin/env python3
"""
Diagnose Dhan API Authentication Issue
Tests the credentials directly to identify the problem
"""

import os
from dotenv import load_dotenv
import json
from datetime import datetime

# Load environment variables from openalgo/.env
env_path = os.path.join(os.path.dirname(__file__), "openalgo", ".env")
load_dotenv(env_path)

# Get credentials
api_key = os.getenv("BROKER_API_KEY")
api_secret = os.getenv("BROKER_API_SECRET")

print("=" * 70)
print("Dhan API Authentication Diagnostics")
print("=" * 70)
print()

# Parse the API key format
if ":::" in api_key:
    client_id, access_token = api_key.split(":::")
    print("✅ Format: client_id:::access_token (OpenAlgo format)")
    print(f"   Client ID: {client_id}")
    print(f"   Access Token (first 30 chars): {access_token[:30]}...")
    print(f"   Access Token length: {len(access_token)} chars")
else:
    print("❌ Invalid format - missing ':::'")
    access_token = api_key
    client_id = None

print(f"   API Secret: {api_secret}")
print()

# Decode JWT to check expiry
try:
    import base64

    # JWT format: header.payload.signature
    parts = access_token.split(".")
    if len(parts) == 3:
        # Decode payload (add padding if needed)
        payload = parts[1]
        payload += "=" * (4 - len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload)
        payload_data = json.loads(decoded)

        print("📋 Token Details:")
        print(f"   Issuer: {payload_data.get('iss', 'N/A')}")
        print(
            f"   Dhan Client ID (from token): {payload_data.get('dhanbClientId', 'N/A')}"
        )

        # Check expiry
        exp_timestamp = payload_data.get("exp")
        iat_timestamp = payload_data.get("iat")

        if exp_timestamp:
            exp_date = datetime.fromtimestamp(exp_timestamp)
            now = datetime.now()
            print(
                f"   Issued at: {datetime.fromtimestamp(iat_timestamp) if iat_timestamp else 'N/A'}"
            )
            print(f"   Expires at: {exp_date}")
            print(f"   Current time: {now}")

            if now > exp_date:
                print(f"   ❌ TOKEN EXPIRED {(now - exp_date).days} days ago!")
            else:
                remaining = exp_date - now
                print(
                    f"   ✅ Token valid for {remaining.days} days, {remaining.seconds // 3600} hours"
                )

        # Check if client IDs match
        token_client_id = payload_data.get("dhanbClientId")
        if client_id and token_client_id:
            if client_id == token_client_id:
                print("   ✅ Client IDs match")
            else:
                print("   ❌ Client ID mismatch!")
                print(f"      .env client_id: {client_id}")
                print(f"      Token client_id: {token_client_id}")

        print()
except Exception as e:
    print(f"⚠️ Could not decode JWT: {e}")
    print()

# Test with Dhan API
print("Testing Dhan API Connection...")
print()

try:
    from dhanhq import dhanhq

    # Initialize client - dhanhq expects (client_id, access_token)
    # But we need to use the format they expect
    if client_id:
        print("Attempting connection with:")
        print(f"  client_id (api_secret): {api_secret}")
        print(f"  access_token (api_key): {access_token[:50]}...")
        print()

        # Try with API secret as client_id and access token
        dhan = dhanhq(api_secret, access_token)
        print("✅ Dhan client initialized")
        print()

        # Test API call
        print("Testing get_fund_limits()...")
        try:
            result = dhan.get_fund_limits()
            print("✅ API call successful!")
            print(f"   Response type: {type(result)}")
            if isinstance(result, dict):
                print(f"   Response keys: {list(result.keys())}")
                if "status" in result:
                    print(f"   Status: {result['status']}")
                if "data" in result:
                    print(f"   Data received: {result['data'] is not None}")
        except Exception as api_error:
            print(f"❌ API call failed: {api_error}")
            print()

            # Try alternative: use client_id from token
            if token_client_id and token_client_id != api_secret:
                print("Retrying with client_id extracted from token...")
                dhan2 = dhanhq(token_client_id, access_token)
                try:
                    result = dhan2.get_fund_limits()
                    print("✅ API call successful with token client_id!")
                    print(f"   Use this client_id: {token_client_id}")
                except Exception as e2:
                    print(f"❌ Also failed: {e2}")
    else:
        print("❌ Cannot test - client_id not found in .env format")

except ImportError:
    print("❌ dhanhq package not installed")
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback

    traceback.print_exc()

print()
print("=" * 70)
print("Diagnosis Complete")
print("=" * 70)
