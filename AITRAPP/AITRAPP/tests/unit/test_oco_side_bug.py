
from unittest.mock import Mock

from packages.core.oco import OCOManager
from packages.storage.models import Order, OrderSideEnum, OrderStatusEnum, OrderTypeEnum


class TestOCOSideBug:
    def test_child_order_sides_are_opposite_to_entry(self):
        # Mock KiteClient since OCOManager needs it
        kite_client = Mock()
        oco_manager = OCOManager(kite_client)

        # Create an Entry Order (LONG/BUY)
        entry_order = Order(
            client_order_id="ENTRY_123",
            symbol="NIFTY23OCTFUT",
            instrument_token=12345,
            side=OrderSideEnum.BUY,
            qty=50,
            order_type=OrderTypeEnum.MARKET,
            price=19500.0,
            status=OrderStatusEnum.FILLED,
            strategy_name="TEST_STRAT"
        )

        # Create OCO group with SL and TP
        group_id = oco_manager.create_oco_group(
            entry_order=entry_order,
            stop_price=19400.0,
            tp1_price=19600.0,
            tp2_price=19700.0
        )

        group = oco_manager.groups[group_id]

        # Verify Entry Order Side
        assert group.entry_order.side == OrderSideEnum.BUY

        # Verify Stop Order Side (Should be SELL, but bug makes it BUY)
        stop_order = group.stop_order
        print(f"Entry Side: {entry_order.side}")
        print(f"Stop Order Side: {stop_order.side}")

        # Assert the EXPECTED behavior (FAILING TEST if bug exists)
        # If entry is BUY, exit (stop) should be SELL
        assert stop_order.side == OrderSideEnum.SELL, f"Stop order side should be SELL, got {stop_order.side}"

        # Verify TP1 Side
        tp1_order = group.tp1_order
        assert tp1_order.side == OrderSideEnum.SELL, f"TP1 order side should be SELL, got {tp1_order.side}"

        # Verify TP2 Side
        tp2_order = group.tp2_order
        assert tp2_order.side == OrderSideEnum.SELL, f"TP2 order side should be SELL, got {tp2_order.side}"
