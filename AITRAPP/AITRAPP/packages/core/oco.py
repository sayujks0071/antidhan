"""OCO (One-Cancels-Other) order management"""
import uuid
from typing import Dict, List, Optional
from datetime import datetime
import structlog

from packages.storage.models import (
    Order, OrderStatusEnum, OrderTypeEnum, OrderSideEnum,
    Position, PositionStatusEnum
)
from packages.storage.database import get_db_session
from packages.core.kite_client import KiteClient
from packages.core.execution import plan_client_id, order_client_id

logger = structlog.get_logger(__name__)


class OCOGroup:
    """Represents an OCO group (entry + stop + TP)"""
    def __init__(self, group_id: str, entry_order: Order, stop_order: Optional[Order] = None, 
                 tp1_order: Optional[Order] = None, tp2_order: Optional[Order] = None):
        self.group_id = group_id
        self.entry_order = entry_order
        self.stop_order = stop_order
        self.tp1_order = tp1_order
        self.tp2_order = tp2_order
        self.created_at = datetime.utcnow()
    
    def get_all_orders(self) -> List[Order]:
        """Get all orders in this group"""
        orders = [self.entry_order]
        if self.stop_order:
            orders.append(self.stop_order)
        if self.tp1_order:
            orders.append(self.tp1_order)
        if self.tp2_order:
            orders.append(self.tp2_order)
        return orders
    
    def get_active_orders(self) -> List[Order]:
        """Get orders that are still active (PLACED or PARTIAL)"""
        return [o for o in self.get_all_orders() 
                if o and o.status in [OrderStatusEnum.PLACED, OrderStatusEnum.PARTIAL]]
    
    def get_filled_orders(self) -> List[Order]:
        """Get orders that have been filled"""
        return [o for o in self.get_all_orders() 
                if o and o.status == OrderStatusEnum.FILLED]


class OCOManager:
    """Manages OCO groups and sibling cancellation"""
    
    def __init__(self, kite_client: KiteClient):
        self.kite_client = kite_client
        self.groups: Dict[str, OCOGroup] = {}
    
    def create_oco_group(self, entry_order: Order, stop_price: float, 
                        tp1_price: Optional[float] = None, tp2_price: Optional[float] = None,
                        instrument_token: Optional[int] = None, qty: Optional[int] = None,
                        plan=None) -> str:
        """Create an OCO group with entry, stop, and optional TPs"""
        group_id = uuid.uuid4().hex[:16]
        
        # Use entry order details if not provided
        if instrument_token is None:
            instrument_token = entry_order.instrument_token
        if qty is None:
            qty = entry_order.qty
        
        # Generate deterministic IDs if plan is provided
        if plan:
            plan_cid = plan_client_id(plan)
            sl_cid = order_client_id(plan_cid, "SL", group_id)
            tp1_cid = order_client_id(plan_cid, "TP1", group_id) if tp1_price else None
            tp2_cid = order_client_id(plan_cid, "TP2", group_id) if tp2_price else None
        else:
            # Fallback to old method if plan not available
            sl_cid = f"{entry_order.client_order_id}_SL"
            tp1_cid = f"{entry_order.client_order_id}_TP1" if tp1_price else None
            tp2_cid = f"{entry_order.client_order_id}_TP2" if tp2_price else None
        
        # Create stop loss order
        stop_order = Order(
            client_order_id=sl_cid,
            symbol=entry_order.symbol,
            instrument_token=instrument_token,
            side=OrderSideEnum.SELL if entry_order.side == OrderSideEnum.BUY else OrderSideEnum.BUY,
            qty=qty,
            order_type=OrderTypeEnum.SLM,  # Stop Loss Market
            trigger_price=stop_price,
            tag="STOP",
            parent_group=group_id,
            is_stop_loss=True,
            strategy_name=entry_order.strategy_name
        )
        
        # Create TP1 if provided
        tp1_order = None
        if tp1_price:
            tp1_order = Order(
                client_order_id=tp1_cid,
                symbol=entry_order.symbol,
                instrument_token=instrument_token,
                side=OrderSideEnum.SELL if entry_order.side == OrderSideEnum.BUY else OrderSideEnum.BUY,
                qty=int(qty * 0.5) if tp2_price else qty,  # Partial if TP2 exists
                order_type=OrderTypeEnum.LIMIT,
                price=tp1_price,
                tag="TP1",
                parent_group=group_id,
                is_take_profit=True,
                strategy_name=entry_order.strategy_name
            )
        
        # Create TP2 if provided
        tp2_order = None
        if tp2_price:
            tp2_order = Order(
                client_order_id=tp2_cid,
                symbol=entry_order.symbol,
                instrument_token=instrument_token,
                side=OrderSideEnum.SELL if entry_order.side == OrderSideEnum.BUY else OrderSideEnum.BUY,
                qty=qty - (tp1_order.qty if tp1_order else 0),
                order_type=OrderTypeEnum.LIMIT,
                price=tp2_price,
                tag="TP2",
                parent_group=group_id,
                is_take_profit=True,
                strategy_name=entry_order.strategy_name
            )
        
        group = OCOGroup(group_id, entry_order, stop_order, tp1_order, tp2_order)
        self.groups[group_id] = group
        
        logger.info("OCO group created", group_id=group_id, 
                   entry=entry_order.client_order_id,
                   has_stop=stop_order is not None,
                   has_tp1=tp1_order is not None,
                   has_tp2=tp2_order is not None)
        
        return group_id
    
    def on_entry_fill(self, group_id: str) -> None:
        """Called when entry order is filled - place stop and TP orders (single-flight)"""
        group = self.groups.get(group_id)
        if not group:
            logger.warning("OCO group not found", group_id=group_id)
            return
        
        if group.entry_order.status != OrderStatusEnum.FILLED:
            logger.warning("Entry order not filled", group_id=group_id)
            return
        
        # Single-flight check: prevent duplicate SL/TP if OrderWatcher replays
        from packages.storage.database import order_exists
        
        with get_db_session() as db:
            sl_cid = group.stop_order.client_order_id if group.stop_order else None
            tp1_cid = group.tp1_order.client_order_id if group.tp1_order else None
            tp2_cid = group.tp2_order.client_order_id if group.tp2_order else None
            
            # Check if children already exist
            if sl_cid and order_exists(sl_cid, status_in=("PLACED", "FILLED")):
                if tp1_cid and order_exists(tp1_cid, status_in=("PLACED", "FILLED")):
                    logger.info("OCO children already placed (single-flight guard)", 
                              group_id=group_id, sl_cid=sl_cid, tp1_cid=tp1_cid)
                    return {"group": group_id, "sl_cid": sl_cid, "tp1_cid": tp1_cid}
            
            # Place stop order
            if group.stop_order:
                try:
                    broker_order_id = self.kite_client.place_order(
                        exchange=group.stop_order.symbol.split(":")[0] if ":" in group.stop_order.symbol else "NFO",
                        tradingsymbol=group.stop_order.symbol,
                        transaction_type=group.stop_order.side.value,
                        quantity=group.stop_order.qty,
                        order_type="SL-M",
                        trigger_price=group.stop_order.trigger_price,
                        product="MIS",
                        validity="DAY"
                    )
                    group.stop_order.broker_order_id = broker_order_id
                    group.stop_order.status = OrderStatusEnum.PLACED
                    db.add(group.stop_order)
                    logger.info("Stop order placed", group_id=group_id, 
                              broker_order_id=broker_order_id)
                except Exception as e:
                    logger.error("Failed to place stop order", group_id=group_id, error=str(e))
                    # Create risk event
                    from packages.storage.models import RiskEvent
                    risk_event = RiskEvent(
                        event_type="STOP_ORDER_FAILED",
                        severity="CRITICAL",
                        message=f"Failed to place stop order for {group_id}",
                        details={"group_id": group_id, "error": str(e)}
                    )
                    db.add(risk_event)
            
            # Place TP1 order
            if group.tp1_order:
                try:
                    broker_order_id = self.kite_client.place_order(
                        exchange=group.tp1_order.symbol.split(":")[0] if ":" in group.tp1_order.symbol else "NFO",
                        tradingsymbol=group.tp1_order.symbol,
                        transaction_type=group.tp1_order.side.value,
                        quantity=group.tp1_order.qty,
                        order_type="LIMIT",
                        price=group.tp1_order.price,
                        product="MIS",
                        validity="DAY"
                    )
                    group.tp1_order.broker_order_id = broker_order_id
                    group.tp1_order.status = OrderStatusEnum.PLACED
                    db.add(group.tp1_order)
                    logger.info("TP1 order placed", group_id=group_id, 
                              broker_order_id=broker_order_id)
                except Exception as e:
                    logger.error("Failed to place TP1 order", group_id=group_id, error=str(e))
            
            # Place TP2 order
            if group.tp2_order:
                try:
                    broker_order_id = self.kite_client.place_order(
                        exchange=group.tp2_order.symbol.split(":")[0] if ":" in group.tp2_order.symbol else "NFO",
                        tradingsymbol=group.tp2_order.symbol,
                        transaction_type=group.tp2_order.side.value,
                        quantity=group.tp2_order.qty,
                        order_type="LIMIT",
                        price=group.tp2_order.price,
                        product="MIS",
                        validity="DAY"
                    )
                    group.tp2_order.broker_order_id = broker_order_id
                    group.tp2_order.status = OrderStatusEnum.PLACED
                    db.add(group.tp2_order)
                    logger.info("TP2 order placed", group_id=group_id, 
                              broker_order_id=broker_order_id)
                except Exception as e:
                    logger.error("Failed to place TP2 order", group_id=group_id, error=str(e))
            
            db.commit()
    
    def on_child_fill(self, group_id: str, filled_order: Order) -> None:
        """Called when any child order (stop/TP) is filled - cancel siblings"""
        group = self.groups.get(group_id)
        if not group:
            logger.warning("OCO group not found", group_id=group_id)
            return
        
        if filled_order.status != OrderStatusEnum.FILLED:
            return
        
        # Cancel all other active orders in the group
        siblings = [o for o in group.get_active_orders() if o.client_order_id != filled_order.client_order_id]
        
        if not siblings:
            logger.info("No siblings to cancel", group_id=group_id)
            return
        
        logger.info("Cancelling siblings", group_id=group_id, 
                   filled_order=filled_order.client_order_id,
                   siblings=[s.client_order_id for s in siblings])
        
        with get_db_session() as db:
            for sibling in siblings:
                try:
                    if sibling.broker_order_id:
                        # Cancel on broker
                        self.kite_client.cancel_order(
                            order_id=sibling.broker_order_id,
                            variety="regular"
                        )
                    
                    sibling.status = OrderStatusEnum.CANCELLED
                    db.add(sibling)
                    logger.info("Sibling cancelled", group_id=group_id, 
                              sibling_id=sibling.client_order_id)
                except Exception as e:
                    logger.error("Failed to cancel sibling", 
                               group_id=group_id,
                               sibling_id=sibling.client_order_id,
                               error=str(e))
                    # Retry logic would go here (with backoff)
            
            db.commit()
    
    def cancel_all_in_group(self, group_id: str) -> None:
        """Cancel all orders in an OCO group (e.g., on EOD or kill switch)"""
        group = self.groups.get(group_id)
        if not group:
            return
        
        active_orders = group.get_active_orders()
        if not active_orders:
            return
        
        logger.info("Cancelling all orders in group", group_id=group_id,
                   num_orders=len(active_orders))
        
        with get_db_session() as db:
            for order in active_orders:
                try:
                    if order.broker_order_id:
                        self.kite_client.cancel_order(
                            order_id=order.broker_order_id,
                            variety="regular"
                        )
                    order.status = OrderStatusEnum.CANCELLED
                    db.add(order)
                except Exception as e:
                    logger.error("Failed to cancel order in group",
                               group_id=group_id,
                               order_id=order.client_order_id,
                               error=str(e))
            
            db.commit()
    
    def get_group_by_order_id(self, client_order_id: str) -> Optional[OCOGroup]:
        """Get OCO group by any order ID in the group"""
        for group in self.groups.values():
            if any(o.client_order_id == client_order_id for o in group.get_all_orders() if o):
                return group
        return None

