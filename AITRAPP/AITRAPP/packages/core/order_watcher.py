"""Order watcher - monitors broker order updates and enforces OCO invariants"""
import asyncio
from datetime import datetime

import structlog

from packages.core.kite_client import KiteClient
from packages.core.oco import OCOManager
from packages.storage.database import get_db_session
from packages.storage.models import (
    Order,
    OrderSideEnum,
    OrderStatusEnum,
    Position,
    PositionStatusEnum,
    SideEnum,
    Trade,
    TradeActionEnum,
)

logger = structlog.get_logger(__name__)


class OrderWatcher:
    """Watches broker order updates and manages OCO groups"""

    def __init__(self, kite_client: KiteClient, orchestrator, oco_manager: OCOManager,
                 redis_bus=None, metrics=None):
        self.kite_client = kite_client
        self.orchestrator = orchestrator
        self.oco_manager = oco_manager
        self.redis_bus = redis_bus
        self.metrics = metrics
        self.running = False
        self.watch_interval = 2.0  # Check every 2 seconds

    async def start(self):
        """Start watching orders"""
        self.running = True
        logger.info("OrderWatcher started")

        while self.running:
            try:
                await self._check_orders()
                await asyncio.sleep(self.watch_interval)
            except Exception as e:
                logger.error("Error in order watcher loop", error=str(e))
                await asyncio.sleep(self.watch_interval)

    def stop(self):
        """Stop watching orders"""
        self.running = False
        logger.info("OrderWatcher stopped")

    async def _check_orders(self):
        """Check for order status updates from broker"""
        from packages.core.heartbeats import touch_order
        touch_order()
        with get_db_session() as db:
            # Get all active orders (PLACED or PARTIAL)
            active_orders = db.query(Order).filter(
                Order.status.in_([OrderStatusEnum.PLACED, OrderStatusEnum.PARTIAL]),
                Order.broker_order_id.isnot(None)
            ).all()

            if not active_orders:
                return

            # Fetch order status from broker
            broker_order_ids = [o.broker_order_id for o in active_orders if o.broker_order_id]
            if not broker_order_ids:
                return

            try:
                # Get orders from Kite
                kite_orders = self.kite_client.get_orders()
                kite_orders_by_id = {o['order_id']: o for o in kite_orders if o.get('order_id')}

                # Update local orders
                for local_order in active_orders:
                    if not local_order.broker_order_id:
                        continue

                    kite_order = kite_orders_by_id.get(local_order.broker_order_id)
                    if not kite_order:
                        continue

                    # Map Kite status to our enum
                    kite_status = kite_order.get('status', '').upper()
                    new_status = self._map_kite_status(kite_status)

                    if new_status != local_order.status:
                        old_status = local_order.status
                        local_order.status = new_status

                        # Update fill details
                        if new_status in [OrderStatusEnum.PARTIAL, OrderStatusEnum.FILLED]:
                            local_order.filled_qty = kite_order.get('filled_quantity', 0)
                            local_order.average_price = kite_order.get('average_price', 0.0)

                        logger.info("Order status updated",
                                  client_order_id=local_order.client_order_id,
                                  broker_order_id=local_order.broker_order_id,
                                  old_status=old_status.value,
                                  new_status=new_status.value)

                        # Sync OCO manager in-memory state
                        if local_order.parent_group:
                            group = self.oco_manager.groups.get(local_order.parent_group)
                            if group:
                                # We need to update the correct order in the group
                                if group.entry_order.client_order_id == local_order.client_order_id:
                                    group.entry_order.status = new_status
                                    group.entry_order.filled_qty = local_order.filled_qty
                                    group.entry_order.average_price = local_order.average_price
                                elif group.stop_order and group.stop_order.client_order_id == local_order.client_order_id:
                                    group.stop_order.status = new_status
                                elif group.tp1_order and group.tp1_order.client_order_id == local_order.client_order_id:
                                    group.tp1_order.status = new_status
                                elif group.tp2_order and group.tp2_order.client_order_id == local_order.client_order_id:
                                    group.tp2_order.status = new_status

                        # Publish to Redis
                        if self.redis_bus:
                            await self.redis_bus.publish_order({
                                "client_order_id": local_order.client_order_id,
                                "broker_order_id": local_order.broker_order_id,
                                "status": new_status.value,
                                "tag": local_order.tag,
                                "parent_group": local_order.parent_group
                            })

                        # Handle OCO logic and call orchestrator
                        if new_status == OrderStatusEnum.FILLED:
                            fill_event = {
                                "client_order_id": local_order.client_order_id,
                                "broker_order_id": local_order.broker_order_id,
                                "filled_qty": local_order.filled_qty,
                                "average_price": local_order.average_price,
                                "tag": local_order.tag,
                                "parent_group": local_order.parent_group
                            }

                            if local_order.tag == "ENTRY":
                                await self.orchestrator.on_entry_filled(fill_event)
                            elif local_order.tag in ["STOP", "TP1", "TP2"]:
                                await self.orchestrator.on_child_filled(fill_event)

                            await self._handle_order_fill(local_order, db)
                        elif new_status == OrderStatusEnum.REJECTED:
                            await self._handle_order_rejection(local_order, db)

                db.commit()

            except Exception as e:
                logger.error("Error fetching order status from broker", error=str(e))
                db.rollback()

    def _map_kite_status(self, kite_status: str) -> OrderStatusEnum:
        """Map Kite order status to our enum"""
        status_map = {
            'OPEN': OrderStatusEnum.PLACED,
            'TRIGGER PENDING': OrderStatusEnum.PLACED,
            'COMPLETE': OrderStatusEnum.FILLED,
            'CANCELLED': OrderStatusEnum.CANCELLED,
            'REJECTED': OrderStatusEnum.REJECTED,
        }
        return status_map.get(kite_status, OrderStatusEnum.PLACED)

    async def _handle_order_fill(self, order: Order, db):
        """Handle order fill - trigger OCO logic"""
        if not order.parent_group:
            return

        # Check if this is an entry order
        if order.tag == "ENTRY":
            # Entry filled - place stop and TP orders
            logger.info("Entry order filled, placing stop/TP orders",
                      group_id=order.parent_group,
                      order_id=order.client_order_id)
            self.oco_manager.on_entry_fill(order.parent_group)

            # Create position
            position = Position(
                position_id=f"POS_{order.client_order_id}",
                symbol=order.symbol,
                instrument_token=order.instrument_token,
                side=SideEnum.LONG if order.side == OrderSideEnum.BUY else SideEnum.SHORT,
                qty=order.filled_qty or order.qty,
                avg_price=order.average_price or order.price or 0.0,
                current_price=order.average_price or order.price or 0.0,
                stop_loss=order.trigger_price,  # Will be updated from stop order
                risk_amount=0.0,  # Will be calculated
                oco_group=order.parent_group,
                strategy_name=order.strategy_name,
                entry_order_id=order.client_order_id,
                status=PositionStatusEnum.OPEN
            )
            db.add(position)

            # Create trade record
            trade = Trade(
                position_id=position.id,
                action=TradeActionEnum.OPEN,
                qty=order.filled_qty or order.qty,
                price=order.average_price or order.price or 0.0,
                fees=0.0,  # Will be calculated
                risk_amount=0.0
            )
            db.add(trade)

        else:
            # Child order (stop/TP) filled - cancel siblings
            logger.info("Child order filled, cancelling siblings",
                      group_id=order.parent_group,
                      order_id=order.client_order_id,
                      tag=order.tag)
            self.oco_manager.on_child_fill(order.parent_group, order)

            # Update position
            position = db.query(Position).filter_by(oco_group=order.parent_group).first()
            if position:
                if order.tag == "STOP":
                    position.status = PositionStatusEnum.CLOSED
                    position.closed_at = datetime.utcnow()
                    position.exit_reason = "STOP_LOSS"
                elif order.tag in ["TP1", "TP2"]:
                    # Partial or full exit
                    if order.tag == "TP1":
                        # Partial exit - move stop to breakeven
                        position.qty -= order.filled_qty
                        # Update stop to breakeven (would need to modify stop order)
                        position.exit_reason = "TP1_PARTIAL"
                    else:
                        # Full exit
                        position.status = PositionStatusEnum.CLOSED
                        position.closed_at = datetime.utcnow()
                        position.exit_reason = "TP2_FULL"

                # Create trade record
                trade = Trade(
                    position_id=position.id,
                    action=TradeActionEnum.PARTIAL_EXIT if order.tag == "TP1" else TradeActionEnum.FULL_EXIT,
                    qty=order.filled_qty,
                    price=order.average_price or order.price or 0.0,
                    fees=0.0,
                    risk_amount=0.0
                )
                db.add(trade)

    async def _handle_order_rejection(self, order: Order, db):
        """Handle order rejection"""
        logger.warning("Order rejected",
                      client_order_id=order.client_order_id,
                      broker_order_id=order.broker_order_id)

        # If entry order rejected, cancel the whole group
        if order.tag == "ENTRY" and order.parent_group:
            self.oco_manager.cancel_all_in_group(order.parent_group)

        # Create risk event
        from packages.storage.models import RiskEvent
        risk_event = RiskEvent(
            event_type="ORDER_REJECTED",
            severity="WARNING",
            message=f"Order {order.client_order_id} was rejected",
            details={
                "client_order_id": order.client_order_id,
                "broker_order_id": order.broker_order_id,
                "symbol": order.symbol,
                "tag": order.tag
            }
        )
        db.add(risk_event)
