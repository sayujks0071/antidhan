import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime
from packages.core.order_watcher import OrderWatcher
from packages.core.oco import OCOManager, OCOGroup
from packages.storage.models import Order, OrderStatusEnum, OrderSideEnum, OrderTypeEnum

@pytest.mark.asyncio
class TestOCOFillBug:
    async def test_stop_loss_not_placed_due_to_stale_status(self):
        # 1. Setup
        mock_kite = MagicMock()
        oco_manager = OCOManager(mock_kite)

        # Create an entry order (simulating one that was placed)
        entry_order = Order(
            client_order_id="ENTRY_1",
            symbol="INFY",
            instrument_token=1234,
            side=OrderSideEnum.BUY,
            qty=10,
            order_type=OrderTypeEnum.MARKET,
            status=OrderStatusEnum.PLACED,
            tag="ENTRY",
            broker_order_id="BROKER_1",
            strategy_name="TEST"
        )

        # Create OCO group in manager (in-memory state)
        stop_order = Order(
            client_order_id="STOP_1",
            symbol="INFY",
            instrument_token=1234,
            side=OrderSideEnum.SELL,
            qty=10,
            order_type=OrderTypeEnum.SLM,
            trigger_price=90.0,
            tag="STOP",
            status=OrderStatusEnum.PLACED,
            parent_group="GROUP_1",
            strategy_name="TEST"
        )

        group = OCOGroup("GROUP_1", entry_order, stop_order)
        oco_manager.groups["GROUP_1"] = group

        mock_orchestrator = MagicMock()
        mock_orchestrator.on_entry_filled = AsyncMock()
        mock_orchestrator.on_child_filled = AsyncMock()

        watcher = OrderWatcher(mock_kite, mock_orchestrator, oco_manager)

        # Mock Kite response
        mock_kite.get_orders.return_value = [{
            "order_id": "BROKER_1",
            "status": "COMPLETE",
            "filled_quantity": 10,
            "average_price": 100.0
        }]

        # Mock DB session
        db_order_instance = Order(
            client_order_id="ENTRY_1",
            symbol="INFY",
            instrument_token=1234,
            side=OrderSideEnum.BUY,
            qty=10,
            order_type=OrderTypeEnum.MARKET,
            status=OrderStatusEnum.PLACED,
            tag="ENTRY",
            broker_order_id="BROKER_1",
            parent_group="GROUP_1",
            strategy_name="TEST"
        )

        mock_db_session = MagicMock()
        # Context manager support
        mock_db_session.__enter__.return_value = mock_db_session
        mock_db_session.__exit__.return_value = None

        mock_query = MagicMock()
        mock_db_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query # Allow chaining
        mock_query.all.return_value = [db_order_instance]

        # Use side_effect to return our mock session specifically
        def get_mock_session(*args, **kwargs):
            return mock_db_session

        with patch("packages.core.order_watcher.get_db_session", side_effect=get_mock_session), \
             patch("packages.storage.database.order_exists", return_value=False), \
             patch("packages.core.oco.get_db_session", side_effect=get_mock_session):

            # 3. Execute
            await watcher._check_orders()

            # print(f"Mock Query Calls: {mock_query.mock_calls}")

        # 4. Verify
        # OrderWatcher should have updated the DB instance
        assert db_order_instance.status == OrderStatusEnum.FILLED, "OrderWatcher did not update local order status"

        # NOW: OCOManager's in-memory order status SHOULD be updated
        assert group.entry_order.status == OrderStatusEnum.FILLED, "OCOManager order status was NOT updated"

        # Verify stop order WAS placed
        # We check if kite.place_order was called.
        # It should be called for the stop order.
        assert mock_kite.place_order.called

        # Check call arguments to be sure it's the stop order
        args, kwargs = mock_kite.place_order.call_args
        assert kwargs.get("order_type") == "SL-M"
        assert kwargs.get("trigger_price") == 90.0
