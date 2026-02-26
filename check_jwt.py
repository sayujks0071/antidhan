#!/usr/bin/env python3
"""
Decode the Dhan JWT token to check expiration.
"""

import base64
import json
from datetime import datetime, timezone

# The token from .env
token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJwX2lwIjoiMjQwMTo0OTAwOjE4ZjA6ZTJmMDozNDZiOjViODk6ZDdjYjoxMzdhIiwic19pcCI6IiIsImlzcyI6ImRoYW4iLCJwYXJ0bmVySWQiOiIiLCJleHAiOjE3NzE0NzYxNTAsImlhdCI6MTc3MTM4OTc1MCwidG9rZW5Db25zdW1lclR5cGUiOiJTRUxGIiwid2ViaG9va1VybCI6Imh0dHA6Ly8xMjcuMC4wLjE6NTAwMiIsImRoYW5DbGllbnRJZCI6IjExMDUwMDkxMzkifQ.1BwRqlaO6wLZViWiiphy-akxhhE7oX16s7_ODjSmgsGKpl8s8BZk7UUHvzzIGdmRjFGnrau1C1Q4ZFI9zWRABQ"

# Split the token
parts = token.split(".")
if len(parts) == 3:
    # Decode the payload (second part)
    payload = parts[1]
    # Add padding if needed
    payload += "=" * (4 - len(payload) % 4)
    decoded = base64.urlsafe_b64decode(payload)
    data = json.loads(decoded)

    print("=== JWT Token Payload ===")
    for key, value in data.items():
        print(f"  {key}: {value}")

    # Check expiration
    exp = data.get("exp")
    iat = data.get("iat")

    if exp:
        exp_dt = datetime.fromtimestamp(exp, tz=timezone.utc)
        now = datetime.now(timezone.utc)

        print("\n=== Token Expiration ===")
        print(f"  Issued at (iat): {datetime.fromtimestamp(iat, tz=timezone.utc)}")
        print(f"  Expires at (exp): {exp_dt}")
        print(f"  Current time: {now}")

        if now > exp_dt:
            print("  Status: ❌ TOKEN EXPIRED")
            print(f"  Expired by: {now - exp_dt}")
        else:
            print("  Status: ✓ Token valid")
            print(f"  Time remaining: {exp_dt - now}")

    print("\n=== Client ID ===")
    print(f"  dhanClientId: {data.get('dhanClientId')}")
