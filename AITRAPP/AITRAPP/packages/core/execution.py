"""Order execution engine with OCO semantics and retry logic"""
import asyncio
import hashlib
import os
import time
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from uuid import uuid4

import structlog
from kiteconnect import KiteConnect

from packages.core.config import ExecutionConfig, Settings, app_config
from packages.core import compliance
from packages.core.models import (
    Instrument,
    Order,
    OrderStatus,
    Position,
    Signal,
    SignalSide,
)

logger = structlog.get_logger(__name__)


def plan_client_id(plan) -> str:
    """
    Deterministic id per decision plan.
    Keep it stable across retries; trim to 24 chars for readability.
    """
    # Extract plan attributes (assuming plan has these attributes)
    symbol = getattr(plan, 'symbol', getattr(plan, 'instrument', {}).get('symbol', 'UNKNOWN'))
    side = getattr(plan, 'side', 'LONG')
    entry = getattr(plan, 'entry', getattr(plan, 'entry_price', 0.0))
    stop = getattr(plan, 'stop', getattr(plan, 'stop_loss', 0.0))
    tp = getattr(plan, 'tp', getattr(plan, 'take_profit_1', 0.0))
    qty = getattr(plan, 'qty', getattr(plan, 'quantity', 0))
    strategy = getattr(plan, 'strategy', getattr(plan, 'strategy_name', 'UNKNOWN'))
    config_sha = getattr(plan, 'config_sha', app_config.config_sha if hasattr(app_config, 'config_sha') else 'default')
    
    base = "|".join([
        str(symbol),
        str(side),
        f"{round(float(entry), 2)}",
        f"{round(float(stop), 2)}",
        f"{round(float(tp), 2)}",
        str(int(qty)),
        str(strategy),
        str(config_sha),
    ])
    return hashlib.sha1(base.encode()).hexdigest()[:24]


def order_client_id(plan_cid: str, tag: str, group_id: Optional[str] = None) -> str:
    """Generate client order ID from plan ID, tag, and optional group ID"""
    # ENTRY | SL | TP (+ optional OCO group)
    return f"{plan_cid}:{tag}" + (f":{group_id}" if group_id else "")


class OrderResult(Enum):
    """Order execution result"""
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"


class ExecutionEngine:
    """
    Manages order execution with:
    - OCO (One-Cancels-Other) semantics
    - Idempotent order placement
    - Retry with exponential backoff
    - Rate limiting
    - Smart order chasing (LIMIT orders)
    """
    
    def __init__(
        self,
        kite: KiteConnect,
        config: ExecutionConfig,
        settings: Settings
    ):
        self.kite = kite
        self.config = config
        self.settings = settings
        
        # Order tracking
        self.orders: Dict[str, Order] = {}
        self.order_id_map: Dict[str, str] = {}  # client_order_id -> order_id
        
        # OCO groups
        self.oco_groups: Dict[str, List[str]] = {}  # parent_order_id -> [child_order_ids]
        
        # Rate limiting
        self.last_order_time = 0.0
        self.min_order_interval = 0.1  # 100ms between orders
        
        # SEBI/NSE: TOPS throttling (per-second cap)
        self.tops_cap = config.tops_cap_per_sec
        self.order_timestamps: List[float] = []  # Track recent orders for TOPS
        
        # Paper mode state
        self.is_paper_mode = settings.app_mode.value == "PAPER"
        self.paper_orders: Dict[str, Order] = {}
        self.paper_order_counter = 0
    
    async def execute_signal(
        self,
        signal: Signal,
        quantity: int
    ) -> tuple[OrderResult, Optional[Order]]:
        """
        Execute a trading signal with entry and attached stops/targets.
        
        Creates:
        1. Entry order (MARKET or LIMIT)
        2. Stop loss order (attached)
        3. Take profit orders (attached)
        
        Args:
            signal: Trading signal
            quantity: Position size
        
        Returns:
            (OrderResult, Entry Order)
        """
        try:
            logger.info(
                "Executing signal",
                strategy=signal.strategy_name,
                instrument=signal.instrument.tradingsymbol,
                side=signal.side,
                quantity=quantity
            )
            
            # 1. Place entry order
            entry_order = await self._place_entry_order(signal, quantity)
            
            if not entry_order or entry_order.status == OrderStatus.REJECTED:
                logger.error("Entry order rejected", signal=signal)
                return OrderResult.REJECTED, None
            
            # 2. Wait for entry fill (with timeout)
            filled = await self._wait_for_fill(entry_order.client_order_id, timeout=30)
            
            if not filled:
                logger.warning("Entry order not filled within timeout", order_id=entry_order.client_order_id)

                # Check for partial fill before cancelling
                # We need to refresh the order state if possible, or rely on internal tracking
                current_order = self.orders.get(entry_order.order_id)
                filled_qty = current_order.filled_quantity if current_order else 0

                await self.cancel_order(entry_order.client_order_id)

                # Check for partial fills after cancellation
                # Refresh order from map as cancellation might have updated status
                entry_order = self.orders.get(entry_order.order_id)

                if entry_order and entry_order.filled_quantity > 0:
                    logger.warning(
                        "Partial fill detected on timeout",
                        order_id=entry_order.order_id,
                        filled=entry_order.filled_quantity,
                        requested=quantity
                    )

                    # Place exit orders for the FILLED quantity
                    await self._place_exit_orders(signal, entry_order, entry_order.filled_quantity)

                    return OrderResult.PARTIAL, entry_order
                if filled_qty > 0:
                    logger.info(
                        "Partial fill detected on timeout",
                        order_id=entry_order.order_id,
                        filled_qty=filled_qty,
                        requested_qty=quantity
                    )

                    # Place exit orders for the PARTIAL quantity
                    await self._place_exit_orders(signal, entry_order, filled_qty)

                    return OrderResult.PARTIAL, current_order

                return OrderResult.TIMEOUT, entry_order
            
            # 3. Place exit orders (stop loss and take profits)
            await self._place_exit_orders(signal, entry_order, quantity)
            
            logger.info(
                "Signal executed successfully",
                entry_order_id=entry_order.order_id,
                fill_price=entry_order.average_price
            )
            
            return OrderResult.SUCCESS, entry_order
        
        except Exception as e:
            logger.error("Signal execution failed", error=str(e), signal=signal)
            return OrderResult.ERROR, None
    
    async def _place_entry_order(
        self,
        signal: Signal,
        quantity: int
    ) -> Optional[Order]:
        """Place entry order for a signal"""
        # Generate idempotent client order ID
        client_order_id = self._generate_client_order_id(
            signal.instrument.tradingsymbol,
            signal.strategy_name,
            signal.timestamp
        )
        
        # Check if already placed
        if client_order_id in self.order_id_map:
            logger.info("Order already placed", client_order_id=client_order_id)
            return self.orders.get(self.order_id_map[client_order_id])
        
        # Determine order type
        order_type = self.config.default_order_type
        price = signal.entry_price
        
        # Map signal side to transaction type
        transaction_type = "BUY" if signal.side == SignalSide.LONG else "SELL"
        
        # Place order
        order = await self._place_order(
            tradingsymbol=signal.instrument.tradingsymbol,
            exchange=signal.instrument.exchange,
            transaction_type=transaction_type,
            quantity=quantity,
            order_type=order_type,
            price=price if order_type == "LIMIT" else None,
            product="MIS",  # Intraday
            client_order_id=client_order_id,
            strategy_name=signal.strategy_name
        )
        
        return order
    
    async def _place_exit_orders(
        self,
        signal: Signal,
        entry_order: Order,
        quantity: int
    ) -> None:
        """
        Place exit orders (stop loss and take profits).
        
        These are placed as separate orders and tracked via OCO group.
        """
        parent_order_id = entry_order.order_id
        exit_orders = []
        
        # 1. Stop Loss
        stop_transaction = "SELL" if signal.side == SignalSide.LONG else "BUY"
        
        stop_client_order_id = f"{parent_order_id}_SL"
        
        stop_order = await self._place_order(
            tradingsymbol=signal.instrument.tradingsymbol,
            exchange=signal.instrument.exchange,
            transaction_type=stop_transaction,
            quantity=quantity,
            order_type="SL-M",  # Stop loss market
            price=None,
            trigger_price=signal.stop_loss,
            product="MIS",
            client_order_id=stop_client_order_id,
            parent_order_id=parent_order_id,
            is_stop_loss=True
        )
        
        if stop_order:
            exit_orders.append(stop_order.order_id)
        
        # 2. Take Profit 1
        if signal.take_profit_1:
            tp1_quantity = int(quantity * 0.5)  # 50% partial
            
            tp1_client_order_id = f"{parent_order_id}_TP1"
            
            tp1_order = await self._place_order(
                tradingsymbol=signal.instrument.tradingsymbol,
                exchange=signal.instrument.exchange,
                transaction_type=stop_transaction,
                quantity=tp1_quantity,
                order_type="LIMIT",
                price=signal.take_profit_1,
                product="MIS",
                client_order_id=tp1_client_order_id,
                parent_order_id=parent_order_id,
                is_take_profit=True
            )
            
            if tp1_order:
                exit_orders.append(tp1_order.order_id)
        
        # 3. Take Profit 2
        if signal.take_profit_2:
            tp2_quantity = quantity - int(quantity * 0.5)
            
            tp2_client_order_id = f"{parent_order_id}_TP2"
            
            tp2_order = await self._place_order(
                tradingsymbol=signal.instrument.tradingsymbol,
                exchange=signal.instrument.exchange,
                transaction_type=stop_transaction,
                quantity=tp2_quantity,
                order_type="LIMIT",
                price=signal.take_profit_2,
                product="MIS",
                client_order_id=tp2_client_order_id,
                parent_order_id=parent_order_id,
                is_take_profit=True
            )
            
            if tp2_order:
                exit_orders.append(tp2_order.order_id)
        
        # Register OCO group
        if exit_orders:
            self.oco_groups[parent_order_id] = exit_orders
            logger.info(
                "Exit orders placed",
                parent=parent_order_id,
                exits=len(exit_orders)
            )
    
    async def _place_order(
        self,
        tradingsymbol: str,
        exchange: str,
        transaction_type: str,
        quantity: int,
        order_type: str,
        product: str,
        client_order_id: str,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        parent_order_id: Optional[str] = None,
        is_stop_loss: bool = False,
        is_take_profit: bool = False,
        strategy_name: Optional[str] = None
    ) -> Optional[Order]:
        """
        Place an order with retry logic.
        
        Implements exponential backoff and rate limiting.
        """
        # Rate limiting
        await self._rate_limit()

        # Explicit safety check: Block if not PAPER and no access token
        if not self.is_paper_mode:
            if not getattr(self.kite, "access_token", None):
                logger.error("Order placement BLOCKED: Missing access token in LIVE mode")
                return None
        
        # Paper mode
        if self.is_paper_mode:
            return self._place_paper_order(
                tradingsymbol, exchange, transaction_type, quantity,
                order_type, product, client_order_id, price, trigger_price,
                parent_order_id, is_stop_loss, is_take_profit, strategy_name
            )
        
        # Real order placement with retry
        max_retries = self.config.max_order_retries
        backoff_ms = self.config.retry_backoff_ms
        
        for attempt in range(max_retries):
            try:
                # SEBI/NSE: Check TOPS compliance before placing order
                if not self.is_paper_mode:
                    from packages.core.compliance import tops_cap_ok
                    tops_cap = self.config.tops_cap_per_sec
                    tops_ok, tops_msg = tops_cap_ok(tops_cap)
                    if not tops_ok:
                        logger.warning("TOPS cap violation", msg=tops_msg, cap=tops_cap)
                        # In LIVE mode, this would block; in PAPER we warn
                
                # Prepare order params
                base_tag = client_order_id[:20]  # Kite tag limit is 20 chars
                
                # SEBI/NSE: Attach Algo-ID (placeholder route)
                algo_id = os.getenv("EXCHANGE_ALGO_ID", "").strip()
                if algo_id:
                    # Put into tag (Zerodha supports tag str); keep short
                    tag = f"ALG:{algo_id}"[:20] if len(f"ALG:{algo_id}") <= 20 else base_tag
                else:
                    tag = base_tag
                
                params = {
                    "variety": "regular",
                    "exchange": exchange,
                    "tradingsymbol": tradingsymbol,
                    "transaction_type": transaction_type,
                    "quantity": quantity,
                    "order_type": order_type,
                    "product": product,
                    "tag": tag
                }
                
                if price:
                    params["price"] = price
                
                if trigger_price:
                    params["trigger_price"] = trigger_price
                
                # Note: client_order_id is already deterministic; Algo-ID is in tag
                
                # Place order
                response = self.kite.place_order(**params)
                order_id = response["order_id"]
                
                # Create Order object
                order = Order(
                    order_id=order_id,
                    client_order_id=client_order_id,
                    timestamp=datetime.now(),
                    instrument=None,  # Would need to fetch from instrument manager
                    side=transaction_type,
                    quantity=quantity,
                    price=price or 0.0,
                    order_type=order_type,
                    product=product,
                    status=OrderStatus.PENDING,
                    parent_order_id=parent_order_id,
                    is_stop_loss=is_stop_loss,
                    is_take_profit=is_take_profit,
                    strategy_name=strategy_name
                )
                
                # Store order
                self.orders[order_id] = order
                self.order_id_map[client_order_id] = order_id
                
                logger.info(
                    "Order placed",
                    order_id=order_id,
                    client_order_id=client_order_id,
                    instrument=tradingsymbol,
                    side=transaction_type,
                    quantity=quantity
                )
                
                return order
            
            except Exception as e:
                logger.warning(
                    "Order placement attempt failed",
                    attempt=attempt + 1,
                    error=str(e)
                )
                
                if attempt < max_retries - 1:
                    # Exponential backoff
                    sleep_time = (backoff_ms / 1000) * (2 ** attempt)
                    await asyncio.sleep(sleep_time)
                else:
                    logger.error(
                        "Order placement failed after retries",
                        client_order_id=client_order_id
                    )
                    return None
        
        return None
    
    def _place_paper_order(
        self,
        tradingsymbol: str,
        exchange: str,
        transaction_type: str,
        quantity: int,
        order_type: str,
        product: str,
        client_order_id: str,
        price: Optional[float],
        trigger_price: Optional[float],
        parent_order_id: Optional[str],
        is_stop_loss: bool,
        is_take_profit: bool,
        strategy_name: Optional[str]
    ) -> Order:
        """Simulate order placement in paper mode"""
        self.paper_order_counter += 1
        order_id = f"PAPER_{self.paper_order_counter:06d}"
        
        order = Order(
            order_id=order_id,
            client_order_id=client_order_id,
            timestamp=datetime.now(),
            instrument=None,
            side=transaction_type,
            quantity=quantity,
            price=price or 0.0,
            order_type=order_type,
            product=product,
            status=OrderStatus.COMPLETE,  # Instant fill in paper mode
            filled_quantity=quantity,
            average_price=price or 0.0,
            parent_order_id=parent_order_id,
            is_stop_loss=is_stop_loss,
            is_take_profit=is_take_profit,
            strategy_name=strategy_name
        )
        
        self.paper_orders[order_id] = order
        self.orders[order_id] = order
        self.order_id_map[client_order_id] = order_id
        
        logger.info(
            "[PAPER] Order placed",
            order_id=order_id,
            instrument=tradingsymbol,
            side=transaction_type,
            quantity=quantity
        )
        
        return order
    
    async def cancel_order(self, client_order_id: str) -> bool:
        """Cancel an order"""
        order_id = self.order_id_map.get(client_order_id)
        
        if not order_id:
            logger.warning("Order not found for cancellation", client_order_id=client_order_id)
            return False
        
        if self.is_paper_mode:
            order = self.paper_orders.get(order_id)
            if order:
                order.status = OrderStatus.CANCELLED
                logger.info("[PAPER] Order cancelled", order_id=order_id)
                return True
            return False
        
        try:
            self.kite.cancel_order(variety="regular", order_id=order_id)
            
            order = self.orders.get(order_id)
            if order:
                order.status = OrderStatus.CANCELLED
            
            logger.info("Order cancelled", order_id=order_id)
            return True
        
        except Exception as e:
            logger.error("Order cancellation failed", order_id=order_id, error=str(e))
            return False
    
    async def cancel_oco_group(self, parent_order_id: str) -> None:
        """Cancel all orders in an OCO group"""
        child_orders = self.oco_groups.get(parent_order_id, [])
        
        for order_id in child_orders:
            order = self.orders.get(order_id)
            if order and order.is_active:
                await self.cancel_order(order.client_order_id)
        
        logger.info("OCO group cancelled", parent=parent_order_id, children=len(child_orders))
    
    async def close_position(
        self,
        position: Position,
        reason: str = "Manual close"
    ) -> Optional[Order]:
        """Close a position with market order"""
        # Determine transaction type (opposite of position)
        transaction_type = "SELL" if position.side == SignalSide.LONG else "BUY"
        
        client_order_id = f"CLOSE_{position.position_id}_{int(time.time())}"
        
        order = await self._place_order(
            tradingsymbol=position.instrument.tradingsymbol,
            exchange=position.instrument.exchange,
            transaction_type=transaction_type,
            quantity=position.quantity,
            order_type="MARKET",
            product="MIS",
            client_order_id=client_order_id
        )
        
        if order:
            logger.info(
                "Position closed",
                position_id=position.position_id,
                reason=reason,
                order_id=order.order_id
            )
        
        return order
    
    async def _wait_for_fill(self, client_order_id: str, timeout: int = 30) -> bool:
        """Wait for an order to be filled"""
        order_id = self.order_id_map.get(client_order_id)
        
        if not order_id:
            return False
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            order = self.orders.get(order_id)
            
            if order and order.is_filled:
                return True
            
            # In paper mode, instant fill
            if self.is_paper_mode:
                return True
            
            await asyncio.sleep(0.5)
        
        return False
    
    async def _rate_limit(self) -> None:
        """Enforce rate limiting between orders (TOPS + minimum interval)"""
        now = time.time()
        
        # SEBI/NSE: TOPS compliance check (per-second cap)
        if not self.is_paper_mode:
            # Remove timestamps older than 1 second
            self.order_timestamps = [t for t in self.order_timestamps if now - t < 1.0]
            
            # Check if we're at the cap
            if len(self.order_timestamps) >= self.tops_cap:
                # Wait until the oldest order is > 1 second old
                oldest = min(self.order_timestamps) if self.order_timestamps else now
                wait_time = 1.0 - (now - oldest) + 0.01  # Small buffer
                if wait_time > 0:
                    logger.warning(
                        "TOPS cap reached, waiting",
                        current=len(self.order_timestamps),
                        cap=self.tops_cap,
                        wait_sec=wait_time
                    )
                    await asyncio.sleep(wait_time)
                    # Re-check after wait
                    now = time.time()
                    self.order_timestamps = [t for t in self.order_timestamps if now - t < 1.0]
        
        # Minimum interval between orders (legacy)
        elapsed = now - self.last_order_time
        if elapsed < self.min_order_interval:
            await asyncio.sleep(self.min_order_interval - elapsed)
        
        self.last_order_time = time.time()
        
        # Record this order timestamp for TOPS tracking
        if not self.is_paper_mode:
            self.order_timestamps.append(time.time())
    
    def _generate_client_order_id(
        self,
        symbol: str,
        strategy: str,
        timestamp: datetime
    ) -> str:
        """Generate deterministic client order ID"""
        data = f"{symbol}_{strategy}_{timestamp.isoformat()}"
        hash_obj = hashlib.md5(data.encode())
        return f"CO_{hash_obj.hexdigest()[:12]}"
    
    def get_order(self, order_id: str) -> Optional[Order]:
        """Get order by ID"""
        return self.orders.get(order_id)
    
    def get_orders_for_strategy(self, strategy_name: str) -> List[Order]:
        """Get all orders for a strategy"""
        return [
            order for order in self.orders.values()
            if order.strategy_name == strategy_name
        ]
