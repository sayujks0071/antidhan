#!/usr/bin/env python3
"""
Fix the auth table to map the correct user_id to the API key.
The API key is associated with user_id 'sks20417' but the auth token is stored under '1105009139'.
We need to update the auth entry to use 'sks20417' as the name.
"""

import os
import sys

# Add openalgo directory to path
sys.path.insert(0, "/Users/mac/openalgo/openalgo")

# Load environment variables from .env
from dotenv import load_dotenv

load_dotenv("/Users/mac/openalgo/openalgo/.env")

from database.auth_db import upsert_auth, init_db
import sqlite3

# Get Dhan credentials from environment
dhan_client_id = os.getenv("DHAN_CLIENT_ID")
dhan_access_token = os.getenv("DHAN_ACCESS_TOKEN")

print(f"DHAN_CLIENT_ID: {dhan_client_id}")
print(f"DHAN_ACCESS_TOKEN length: {len(dhan_access_token) if dhan_access_token else 0}")

# Initialize database
init_db()

# The API key is associated with user_id 'sks20417'
# We need to store the auth token under name='sks20417' for the lookup to work
print("\nInserting auth token for user: sks20417")
upsert_auth(
    name="sks20417",  # This must match the user_id in api_keys table
    auth_token=dhan_access_token,
    broker="dhan",
    feed_token=None,
    user_id=dhan_client_id,
    revoke=False,
)

print("Auth token inserted successfully!")

# Verify the insertion
conn = sqlite3.connect("/Users/mac/openalgo/openalgo/db/openalgo.db")
cursor = conn.cursor()

cursor.execute('SELECT name, broker, user_id FROM auth WHERE name="sks20417"')
row = cursor.fetchone()
if row:
    print("\nVerification - Auth entry for sks20417:")
    print(f"  name: {row[0]}")
    print(f"  broker: {row[1]}")
    print(f"  user_id: {row[2]}")
else:
    print("No auth entry found for sks20417!")

conn.close()
