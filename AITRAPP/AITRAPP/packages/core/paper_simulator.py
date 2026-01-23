"""Paper trading simulator"""
from datetime import datetime
from typing import Dict, List, Optional

import structlog

from packages.core.models import Order, OrderStatus, Position, PositionStatus, SignalSide

logger = structlog.get_logger(__name__)


class PaperSimulator:
    """
    Simulates order execution in paper mode.
    
    Features:
    - Instant fills at market price
    - Realistic slippage simulation
    - Fee calculation
    - Position tracking
    """
    
    def __init__(self, slippage_bps: float = 5, fees_per_order: float = 20):
        self.slippage_bps = slippage_bps
        self.fees_per_order = fees_per_order
        
        # Tracking
        self.orders: Dict[str, Order] = {}
        self.positions: Dict[str, Position] = {}
        self.trades: List[dict] = []
        
        # Counters
        self.order_counter = 0
        self.position_counter = 0
    
    def simulate_order(
        self,
        instrument_token: int,
        instrument_symbol: str,
        side: str,  # BUY or SELL
        quantity: int,
        order_type: str,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        current_market_price: float = 0.0
    ) -> Order:
        """
        Simulate order execution.
        
        In paper mode, orders are filled instantly at current market price
        with simulated slippage.
        """
        self.order_counter += 1
        order_id = f"PAPER_{self.order_counter:08d}"
        
        # Calculate fill price with slippage
        if order_type == "MARKET" or price is None:
            fill_price = self._apply_slippage(current_market_price, side)
        else:
            # For LIMIT orders, fill at limit price (simplified)
            fill_price = price
        
        # Create order
        order = Order(
            order_id=order_id,
            client_order_id=f"CLIENT_{order_id}",
            timestamp=datetime.now(),
            instrument=None,  # Would need instrument object
            side=side,
            quantity=quantity,
            price=fill_price,
            order_type=order_type,
            product="MIS",
            status=OrderStatus.COMPLETE,
            filled_quantity=quantity,
            average_price=fill_price
        )
        
        self.orders[order_id] = order
        
        logger.info(
            "[PAPER] Order filled",
            order_id=order_id,
            symbol=instrument_symbol,
            side=side,
            quantity=quantity,
            fill_price=fill_price
        )
        
        return order
    
    def open_position(
        self,
        instrument,
        entry_order: Order,
        signal_side: SignalSide,
        stop_loss: float,
        take_profit_1: Optional[float] = None,
        take_profit_2: Optional[float] = None
    ) -> Position:
        """Open a new simulated position"""
        self.position_counter += 1
        position_id = f"POS_{self.position_counter:08d}"
        
        position = Position(
            position_id=position_id,
            instrument=instrument,
            entry_time=entry_order.timestamp,
            entry_price=entry_order.average_price,
            quantity=entry_order.filled_quantity,
            side=signal_side,
            current_price=entry_order.average_price,
            stop_loss=stop_loss,
            take_profit_1=take_profit_1,
            take_profit_2=take_profit_2,
            risk_amount=0.0,  # Calculate externally
            status=PositionStatus.OPEN,
            entry_order_id=entry_order.order_id
        )
        
        self.positions[position_id] = position
        
        logger.info(
            "[PAPER] Position opened",
            position_id=position_id,
            symbol=instrument.tradingsymbol if instrument else "UNKNOWN",
            side=signal_side,
            quantity=entry_order.filled_quantity,
            entry_price=entry_order.average_price
        )
        
        return position
    
    def close_position(
        self,
        position: Position,
        current_price: float,
        reason: str = "Manual"
    ) -> Order:
        """Close a simulated position"""
        # Simulate exit order
        exit_side = "SELL" if position.side == SignalSide.LONG else "BUY"
        
        exit_order = self.simulate_order(
            instrument_token=position.instrument.token if position.instrument else 0,
            instrument_symbol=position.instrument.tradingsymbol if position.instrument else "UNKNOWN",
            side=exit_side,
            quantity=position.quantity,
            order_type="MARKET",
            current_market_price=current_price
        )
        
        # Update position
        position.status = PositionStatus.CLOSED
        position.close_time = datetime.now()
        position.close_price = exit_order.average_price
        position.exit_order_id = exit_order.order_id
        
        # Calculate P&L
        if position.side == SignalSide.LONG:
            gross_pnl = (exit_order.average_price - position.entry_price) * position.quantity
        else:
            gross_pnl = (position.entry_price - exit_order.average_price) * position.quantity
        
        # Subtract fees
        fees = self.fees_per_order * 2  # Entry + Exit
        net_pnl = gross_pnl - fees
        
        position.realized_pnl = net_pnl
        
        # Record trade
        trade = {
            "position_id": position.position_id,
            "instrument": position.instrument.tradingsymbol if position.instrument else "UNKNOWN",
            "side": position.side.value,
            "quantity": position.quantity,
            "entry_price": position.entry_price,
            "exit_price": exit_order.average_price,
            "gross_pnl": gross_pnl,
            "fees": fees,
            "net_pnl": net_pnl,
            "duration_seconds": (position.close_time - position.entry_time).total_seconds(),
            "exit_reason": reason
        }
        
        self.trades.append(trade)
        
        logger.info(
            "[PAPER] Position closed",
            position_id=position.position_id,
            net_pnl=net_pnl,
            reason=reason
        )
        
        return exit_order
    
    def _apply_slippage(self, price: float, side: str) -> float:
        """Apply simulated slippage to fill price"""
        slippage_mult = self.slippage_bps / 10000.0
        
        if side == "BUY":
            # Buy at slightly higher price
            return price * (1 + slippage_mult)
        else:
            # Sell at slightly lower price
            return price * (1 - slippage_mult)
    
    def get_open_positions(self) -> List[Position]:
        """Get all open positions"""
        return [p for p in self.positions.values() if p.is_open]
    
    def get_trade_summary(self) -> dict:
        """Get summary of simulated trades"""
        if not self.trades:
            return {
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "total_pnl": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0
            }
        
        wins = [t for t in self.trades if t["net_pnl"] > 0]
        losses = [t for t in self.trades if t["net_pnl"] <= 0]
        
        return {
            "total_trades": len(self.trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": (len(wins) / len(self.trades)) * 100 if self.trades else 0.0,
            "total_pnl": sum([t["net_pnl"] for t in self.trades]),
            "avg_win": sum([t["net_pnl"] for t in wins]) / len(wins) if wins else 0.0,
            "avg_loss": sum([t["net_pnl"] for t in losses]) / len(losses) if losses else 0.0,
            "largest_win": max([t["net_pnl"] for t in wins]) if wins else 0.0,
            "largest_loss": min([t["net_pnl"] for t in losses]) if losses else 0.0
        }

