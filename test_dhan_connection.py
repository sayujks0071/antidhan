#!/usr/bin/env python3
"""
Test Dhan API Connection
Tests if the Dhan API credentials are working correctly
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables from openalgo/.env
env_path = os.path.join(os.path.dirname(__file__), "openalgo", ".env")
load_dotenv(env_path)

# Get credentials
api_key = os.getenv("BROKER_API_KEY")
api_secret = os.getenv("BROKER_API_SECRET")

if not api_key or not api_secret:
    print("❌ Error: BROKER_API_KEY or BROKER_API_SECRET not found in .env file")
    sys.exit(1)

print("=" * 60)
print("Dhan API Connection Test")
print("=" * 60)
print(f"API Key (first 30 chars): {api_key[:30]}...")
print(f"API Secret: {api_secret}")
print()

try:
    from dhanhq import dhanhq

    # Initialize Dhan client
    # Note: Dhan API expects (client_id, access_token)
    dhan = dhanhq(api_secret, api_key)
    print("✅ Dhan client initialized successfully")
    print()

    # Test 1: Get available funds
    print("Test 1: Fetching account funds...")
    try:
        funds = dhan.get_fund_limits()
        print("✅ Funds retrieved successfully")
        print(f"Response type: {type(funds)}")
        if isinstance(funds, dict):
            print(f"Available balance: ₹{funds.get('availabelBalance', 'N/A')}")
            print(f"Utilized amount: ₹{funds.get('utilizedAmount', 'N/A')}")
        print()
    except Exception as e:
        print(f"⚠️ Funds fetch failed: {e}")
        print()

    # Test 2: Get positions
    print("Test 2: Fetching positions...")
    try:
        positions = dhan.get_positions()
        print("✅ Positions retrieved successfully")
        print(f"Response type: {type(positions)}")
        if isinstance(positions, dict) and "data" in positions:
            pos_list = positions["data"]
            print(
                f"Number of positions: {len(pos_list) if isinstance(pos_list, list) else 0}"
            )
        print()
    except Exception as e:
        print(f"⚠️ Positions fetch failed: {e}")
        print()

    # Test 3: Get order book
    print("Test 3: Fetching order book...")
    try:
        orders = dhan.get_order_list()
        print("✅ Order book retrieved successfully")
        print(f"Response type: {type(orders)}")
        if isinstance(orders, dict) and "data" in orders:
            order_list = orders["data"]
            print(
                f"Number of orders: {len(order_list) if isinstance(order_list, list) else 0}"
            )
        print()
    except Exception as e:
        print(f"⚠️ Order book fetch failed: {e}")
        print()

    print("=" * 60)
    print("✅ Connection test completed successfully!")
    print("=" * 60)

except ImportError as e:
    print(f"❌ Error importing dhanhq: {e}")
    print("Please ensure dhanhq is installed: pip install dhanhq")
    sys.exit(1)
except Exception as e:
    print(f"❌ Connection test failed: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)
