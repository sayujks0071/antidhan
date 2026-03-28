#!/usr/bin/env python3
"""
Verify the Dhan access token is valid and check what's stored in the database.
"""

import os
import sys

# Add openalgo directory to path
sys.path.insert(0, "/Users/mac/openalgo/openalgo")

# Load environment variables from .env
from dotenv import load_dotenv

load_dotenv("/Users/mac/openalgo/openalgo/.env")

from database.auth_db import decrypt_token
import sqlite3

# Get Dhan credentials from environment
dhan_client_id = os.getenv("DHAN_CLIENT_ID")
dhan_access_token = os.getenv("DHAN_ACCESS_TOKEN")

print("=== Environment ===")
print(f"DHAN_CLIENT_ID: {dhan_client_id}")
print(
    f"DHAN_ACCESS_TOKEN (first 50 chars): {dhan_access_token[:50] if dhan_access_token else 'None'}..."
)
print(f"DHAN_ACCESS_TOKEN length: {len(dhan_access_token) if dhan_access_token else 0}")

# Check what's in the database
print("\n=== Database ===")
conn = sqlite3.connect("/Users/mac/openalgo/openalgo/db/openalgo.db")
cursor = conn.cursor()

cursor.execute("SELECT name, auth, broker, user_id FROM auth")
rows = cursor.fetchall()

for row in rows:
    name, encrypted_auth, broker, user_id = row
    print(f"\nUser: {name}")
    print(f"  Broker: {broker}")
    print(f"  User ID: {user_id}")
    print(f"  Encrypted auth length: {len(encrypted_auth) if encrypted_auth else 0}")

    # Try to decrypt
    if encrypted_auth:
        try:
            decrypted = decrypt_token(encrypted_auth)
            if decrypted:
                print(f"  Decrypted auth (first 50 chars): {decrypted[:50]}...")
                print(f"  Decrypted auth length: {len(decrypted)}")

                # Check if it matches the env token
                if dhan_access_token and decrypted == dhan_access_token:
                    print("  ✓ Matches DHAN_ACCESS_TOKEN from .env")
                else:
                    print("  ✗ Does NOT match DHAN_ACCESS_TOKEN from .env")
            else:
                print("  Decryption returned None!")
        except Exception as e:
            print(f"  Decryption error: {e}")

conn.close()

# Now let's test the token directly with Dhan API
print("\n=== Testing Token with Dhan API ===")
import requests

# Use the token from .env
url = "https://api.dhan.co/v2/marketfeed/quote"
headers = {"Content-Type": "application/json", "access-token": dhan_access_token}
payload = {"symbols": [{"symbolToken": "CRUDEOIL19FEB26FUT", "exchangeSegment": "MCX"}]}

try:
    response = requests.post(url, headers=headers, json=payload, timeout=10)
    print(f"Response Status: {response.status_code}")
    print(f"Response: {response.text[:500]}")
except Exception as e:
    print(f"Error: {e}")
