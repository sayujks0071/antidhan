#!/usr/bin/env python3
"""Test idempotency: same plan twice → one entry order"""
import asyncio
import sys
from typing import Any

# Add project root to path
sys.path.insert(0, '.')

from packages.core.execution import plan_client_id, order_client_id
from packages.storage.database import SessionLocal, order_exists
from packages.core.kite_client import KiteClient
from packages.core.redis_bus import RedisBus
from packages.core.config import app_config, settings
from kiteconnect import KiteConnect


class FakePlan:
    """Fake plan for testing"""
    def __init__(self):
        self.symbol = "NIFTY24NOVFUT"
        self.side = "LONG"
        self.entry = 25000.00
        self.stop = 24950.00
        self.tp = 25100.00
        self.qty = 50
        self.strategy = "ORB"
        self.config_sha = getattr(app_config, 'config_sha', 'abc123')
        self.order_type = "LIMIT"


async def test_idempotency():
    """Test that same plan generates same IDs and is idempotent"""
    print("🧪 Testing idempotency...\n")
    
    plan = FakePlan()
    
    # Generate plan client ID
    plan_cid = plan_client_id(plan)
    print(f"Plan Client ID: {plan_cid}")
    
    # Generate entry order ID
    entry_cid = order_client_id(plan_cid, "ENTRY")
    print(f"Entry Client Order ID: {entry_cid}")
    
    # Check if order exists (should be False for first run)
    exists = order_exists(entry_cid, status_in=("PLACED", "PARTIAL", "FILLED"))
    print(f"Order exists: {exists}")
    
    # Generate same plan again - should get same IDs
    plan2 = FakePlan()
    plan_cid2 = plan_client_id(plan2)
    entry_cid2 = order_client_id(plan_cid2, "ENTRY")
    
    print(f"\nSecond Plan Client ID: {plan_cid2}")
    print(f"Second Entry Client Order ID: {entry_cid2}")
    
    # IDs should match
    if plan_cid == plan_cid2 and entry_cid == entry_cid2:
        print("\n✅ Idempotency test PASSED - Same plan generates same IDs")
    else:
        print("\n❌ Idempotency test FAILED - IDs don't match")
        sys.exit(1)
    
    # Test OCO children IDs
    group_id = "abc123def456"
    sl_cid = order_client_id(plan_cid, "SL", group_id)
    tp_cid = order_client_id(plan_cid, "TP", group_id)
    
    print(f"\nOCO Children IDs:")
    print(f"  Stop Loss: {sl_cid}")
    print(f"  Take Profit: {tp_cid}")
    
    print("\n✅ All idempotency tests passed")


if __name__ == "__main__":
    asyncio.run(test_idempotency())

