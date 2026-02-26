#!/usr/bin/env python3
"""
Regenerate the API key hash with the correct pepper and update the database.
"""

import os
import sys

# Add openalgo directory to path
sys.path.insert(0, "/Users/mac/openalgo/openalgo")

# Load environment variables from .env
from dotenv import load_dotenv

load_dotenv("/Users/mac/openalgo/openalgo/.env")

from argon2 import PasswordHasher
from database.auth_db import init_db, db_session, ApiKeys
from datetime import datetime

# Get the pepper
pepper = os.getenv("API_KEY_PEPPER")
print(f"PEPPER: {pepper}")

# The API key to use
api_key = "41e8e86c16dcea0a5e983e0da925a55e6028eaa0aaf634cf516adc8a6a2bbac2"

# Pepper the key
peppered_key = api_key + pepper
print(f"Peppered key (first 20 chars): {peppered_key[:20]}...")

# Generate hash
ph = PasswordHasher()
api_key_hash = ph.hash(peppered_key)
print(f"Generated hash: {api_key_hash}")

# Initialize database
init_db()

# Update the API key in the database
try:
    api_key_obj = ApiKeys.query.filter_by(user_id="sks20417").first()
    if api_key_obj:
        api_key_obj.api_key_hash = api_key_hash
        api_key_obj.created_at = datetime.now()
        db_session.commit()
        print("Updated API key hash for user sks20417")
    else:
        # Create new entry
        new_key = ApiKeys(
            user_id="sks20417",
            api_key_hash=api_key_hash,
            api_key_encrypted="",  # Will be set by encryption
            created_at=datetime.now(),
            order_mode="auto",
        )
        db_session.add(new_key)
        db_session.commit()
        print("Created new API key entry for user sks20417")
except Exception as e:
    print(f"Error: {e}")
    db_session.rollback()

# Verify the hash
print("\nVerifying hash...")
try:
    ph.verify(api_key_hash, peppered_key)
    print("Hash verification successful!")
except Exception as e:
    print(f"Hash verification failed: {e}")
