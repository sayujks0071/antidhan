#!/usr/bin/env python3
"""
Test Dhan API with correct headers format.
"""

import os
import requests

# Load environment variables
from dotenv import load_dotenv

load_dotenv("/Users/mac/openalgo/openalgo/.env")

access_token = os.getenv("DHAN_ACCESS_TOKEN")
broker_api_key = os.getenv("BROKER_API_KEY")

# Extract client_id from BROKER_API_KEY (format: client_id:::api_key)
if ":::" in broker_api_key:
    client_id = broker_api_key.split(":::")[0]
else:
    client_id = broker_api_key

print("=== Dhan API Test ===")
print(f"Client ID: {client_id}")
print(f"Access Token (first 50): {access_token[:50] if access_token else 'None'}...")

# Test with correct headers
url = "https://api.dhan.co/v2/marketfeed/quote"
headers = {
    "access-token": access_token,
    "client-id": client_id,
    "Content-Type": "application/json",
    "Accept": "application/json",
}

# Try different payload formats
print("\n=== Test 1: Exchange type format ===")
# Format: {exchange_type: [security_ids]}
# MCX = 3
payload1 = {"3": [44993]}  # CRUDEOIL19FEB26FUT security_id
print(f"Payload: {payload1}")
try:
    response = requests.post(url, headers=headers, json=payload1, timeout=10)
    print(f"Response Status: {response.status_code}")
    print(f"Response: {response.text[:500]}")
except Exception as e:
    print(f"Error: {e}")

print("\n=== Test 2: Try with NIFTY ===")
# NSE = 1, NIFTY security_id = 13
payload2 = {"1": [13]}
print(f"Payload: {payload2}")
try:
    response = requests.post(url, headers=headers, json=payload2, timeout=10)
    print(f"Response Status: {response.status_code}")
    print(f"Response: {response.text[:500]}")
except Exception as e:
    print(f"Error: {e}")

print("\n=== Test 3: Check user funds ===")
url_funds = "https://api.dhan.co/fundlimit"
try:
    response = requests.get(url_funds, headers=headers, timeout=10)
    print(f"Response Status: {response.status_code}")
    print(f"Response: {response.text[:500]}")
except Exception as e:
    print(f"Error: {e}")
