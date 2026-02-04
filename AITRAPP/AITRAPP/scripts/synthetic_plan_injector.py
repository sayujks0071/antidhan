#!/usr/bin/env python3
"""Synthetic plan injector for testing idempotency and OCO paths"""
import argparse
import asyncio
import sys

sys.path.insert(0, '.')

from kiteconnect import KiteConnect

from packages.core.config import app_config, settings
from packages.core.execution import order_client_id, plan_client_id
from packages.core.kite_client import KiteClient
from packages.core.oco import OCOManager
from packages.core.redis_bus import RedisBus
from packages.storage.database import SessionLocal, get_db_session, order_exists
from packages.storage.models import Decision, DecisionStatusEnum


class SyntheticPlan:
    """Synthetic plan for testing"""
    def __init__(self, symbol="NIFTY24NOVFUT", side="LONG", entry=25000.0, stop=24950.0, tp=25100.0, qty=50, strategy="ORB"):
        self.symbol = symbol
        self.side = side
        self.entry = entry
        self.stop = stop
        self.tp = tp
        self.qty = qty
        self.strategy = strategy
        self.config_sha = getattr(app_config, 'config_sha', 'test123')
        self.order_type = "LIMIT"


async def inject_plan(plan: SyntheticPlan, broker: KiteClient, storage, bus: RedisBus, oco: OCOManager):
    """Inject a synthetic plan and test idempotency"""
    print(f"📥 Injecting plan: {plan.symbol} @ {plan.entry}")

    # Generate deterministic IDs
    plan_cid = plan_client_id(plan)
    entry_cid = order_client_id(plan_cid, "ENTRY")

    print(f"  Plan ID: {plan_cid}")
    print(f"  Entry Order ID: {entry_cid}")

    # Check idempotency - check for existing decision first
    with get_db_session() as db:
        existing_decision = db.query(Decision).filter_by(client_plan_id=plan_cid).first()
        if existing_decision:
            print("  ⚠️  Decision already exists - skipping (idempotency working)")
            return {"skipped": True, "reason": "duplicate_decision", "client_plan_id": plan_cid}

        # Also check for existing order
        if order_exists(entry_cid, status_in=("PLACED", "PARTIAL", "FILLED")):
            print("  ⚠️  Order already exists - skipping (idempotency working)")
            return {"skipped": True, "reason": "duplicate_entry", "client_order_id": entry_cid}

    # Persist decision
    with get_db_session() as db:
        # Create a fake signal model for decision
        from packages.storage.models import SideEnum, Signal
        signal = Signal(
            symbol=plan.symbol,
            instrument_token=0,  # Fake
            side=SideEnum.LONG,
            strategy=plan.strategy,
            entry_price=plan.entry,
            stop_loss=plan.stop,
            take_profit_1=plan.tp,
            config_sha=plan.config_sha
        )
        db.add(signal)
        db.flush()

        decision = Decision(
            signal_id=signal.id,
            client_plan_id=plan_cid,
            mode="PAPER",
            status=DecisionStatusEnum.PLANNED,
            risk_perc=0.5,
            risk_amount=250.0,
            position_size=plan.qty
        )
        db.add(decision)
        db.commit()
        db.refresh(decision)

        decision_id = decision.id

    # Simulate order placement (don't actually place on broker)
    print("  ✅ Decision persisted")
    print("  📝 Order would be placed (simulated)")

    # Test OCO children IDs
    group_id = "test123"
    sl_cid = order_client_id(plan_cid, "SL", group_id)
    tp_cid = order_client_id(plan_cid, "TP", group_id)

    print("  OCO Children IDs:")
    print(f"    Stop Loss: {sl_cid}")
    print(f"    Take Profit: {tp_cid}")

    return {
        "ok": True,
        "client_order_id": entry_cid,
        "plan_id": plan_cid,
        "decision_id": decision_id,
        "oco_children": {"sl": sl_cid, "tp": tp_cid}
    }


async def test_multiple_injections():
    """Test injecting same plan multiple times"""
    print("🧪 Testing multiple injections of same plan...\n")

    plan = SyntheticPlan()

    # Initialize components
    kite = KiteConnect(api_key=settings.kite_api_key)
    kite.set_access_token(settings.kite_access_token)
    broker = KiteClient(kite)
    bus = RedisBus()
    await bus.connect()
    oco = OCOManager(broker)

    # First injection
    print("1️⃣ First injection:")
    result1 = await inject_plan(plan, broker, SessionLocal, bus, oco)
    print()

    # Second injection (should be skipped)
    print("2️⃣ Second injection (should be skipped):")
    result2 = await inject_plan(plan, broker, SessionLocal, bus, oco)
    print()

    # Verify idempotency
    if result2.get("skipped"):
        print("✅ Idempotency test PASSED - Second injection skipped")
    else:
        print("❌ Idempotency test FAILED - Second injection not skipped")

    await bus.disconnect()


async def main():
    """Main entry point with CLI args"""
    parser = argparse.ArgumentParser(description="Inject synthetic trading plan for testing")
    parser.add_argument("--symbol", default="NIFTY", help="Symbol to trade")
    parser.add_argument("--side", default="LONG", choices=["LONG", "SHORT"], help="Trade side")
    parser.add_argument("--qty", type=int, default=50, help="Quantity")
    parser.add_argument("--strategy", default="ORB", help="Strategy name")
    parser.add_argument("--entry", type=float, help="Entry price (default: auto)")
    parser.add_argument("--stop", type=float, help="Stop loss price (default: auto)")
    parser.add_argument("--tp", type=float, help="Take profit price (default: auto)")

    args = parser.parse_args()

    # Auto-calculate prices if not provided
    entry = args.entry or 25000.0
    stop = args.stop or (entry * 0.998)  # 0.2% below entry
    tp = args.tp or (entry * 1.004)  # 0.4% above entry

    plan = SyntheticPlan(
        symbol=args.symbol,
        side=args.side,
        entry=entry,
        stop=stop,
        tp=tp,
        qty=args.qty,
        strategy=args.strategy
    )

    # Initialize components
    kite = KiteConnect(api_key=settings.kite_api_key)
    kite.set_access_token(settings.kite_access_token)
    broker = KiteClient(kite)
    bus = RedisBus()
    await bus.connect()
    oco = OCOManager(broker)

    try:
        result = await inject_plan(plan, broker, SessionLocal, bus, oco)
        if result.get("skipped"):
            print("✅ Injection skipped (idempotency working)")
            sys.exit(0)
        else:
            print("✅ Plan injected successfully")
            sys.exit(0)
    except Exception as e:
        print(f"❌ Injection failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await bus.disconnect()


if __name__ == "__main__":
    asyncio.run(main())

