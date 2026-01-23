"""Risk management and position sizing"""
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

import structlog

from packages.core.config import RiskConfig
from packages.core.models import (
    Instrument,
    Position,
    RiskCheckResult,
    Signal,
    SignalSide,
)

logger = structlog.get_logger(__name__)


@dataclass
class PortfolioRisk:
    """Current portfolio risk metrics"""
    net_liquid: float
    used_margin: float
    available_margin: float
    
    # Positions
    open_positions: List[Position]
    total_risk_amount: float  # Sum of all position risks
    
    # P&L
    unrealized_pnl: float
    realized_pnl_today: float
    daily_pnl: float
    
    # Limits
    daily_loss_limit: float
    max_portfolio_heat: float
    
    @property
    def portfolio_heat_pct(self) -> float:
        """Portfolio heat as percentage of net liquid"""
        if self.net_liquid > 0:
            return (self.total_risk_amount / self.net_liquid) * 100
        return 0.0
    
    @property
    def daily_pnl_pct(self) -> float:
        """Daily PnL as percentage of net liquid"""
        if self.net_liquid > 0:
            return (self.daily_pnl / self.net_liquid) * 100
        return 0.0
    
    @property
    def is_daily_loss_breached(self) -> bool:
        """Check if daily loss limit is breached"""
        return self.daily_pnl < self.daily_loss_limit
    
    @property
    def is_heat_limit_breached(self) -> bool:
        """Check if portfolio heat limit is breached"""
        return self.portfolio_heat_pct >= self.max_portfolio_heat
    
    @property
    def can_take_new_position(self) -> bool:
        """Check if new position can be taken"""
        return not (self.is_daily_loss_breached or self.is_heat_limit_breached)


class RiskManager:
    """
    Manages risk for trading operations.
    
    Responsibilities:
    - Validate signals against risk limits
    - Calculate position sizes
    - Monitor portfolio heat
    - Enforce daily loss limits
    - Handle lot sizing and freeze quantities
    """
    
    def __init__(self, config: RiskConfig):
        self.config = config
        
        # Daily tracking
        self.daily_start_capital: Optional[float] = None
        self.trades_today = 0
    
    def check_signal(
        self,
        signal: Signal,
        portfolio_risk: PortfolioRisk
    ) -> RiskCheckResult:
        """
        Check if a signal passes risk criteria.
        
        Args:
            signal: Trading signal to check
            portfolio_risk: Current portfolio risk state
        
        Returns:
            RiskCheckResult with approval status and position size
        """
        reasons = []
        
        # 1. Check daily loss limit
        if portfolio_risk.is_daily_loss_breached:
            reasons.append(f"Daily loss limit breached: {portfolio_risk.daily_pnl_pct:.2f}%")
            return RiskCheckResult(approved=False, reasons=reasons)
        
        # 2. Check portfolio heat limit
        if portfolio_risk.is_heat_limit_breached:
            reasons.append(f"Portfolio heat limit breached: {portfolio_risk.portfolio_heat_pct:.2f}%")
            return RiskCheckResult(approved=False, reasons=reasons)
        
        # 3. Calculate position size
        position_size = self.calculate_position_size(
            signal=signal,
            net_liquid=portfolio_risk.net_liquid,
            instrument=signal.instrument
        )
        
        if position_size <= 0:
            reasons.append("Position size calculated as zero or negative")
            return RiskCheckResult(approved=False, reasons=reasons)
        
        # 4. Check per-trade risk
        trade_risk_amount = signal.stop_distance * position_size
        trade_risk_pct = (trade_risk_amount / portfolio_risk.net_liquid) * 100
        
        if trade_risk_pct > self.config.per_trade_risk_pct:
            reasons.append(
                f"Per-trade risk {trade_risk_pct:.2f}% exceeds limit {self.config.per_trade_risk_pct}%"
            )
            return RiskCheckResult(approved=False, reasons=reasons)
        
        # 5. Check if adding this risk breaches portfolio heat
        new_total_risk = portfolio_risk.total_risk_amount + trade_risk_amount
        new_heat_pct = (new_total_risk / portfolio_risk.net_liquid) * 100
        
        if new_heat_pct > self.config.max_portfolio_heat_pct:
            reasons.append(
                f"Portfolio heat limit breached: new heat {new_heat_pct:.2f}% would exceed limit {self.config.max_portfolio_heat_pct}%"
            )
            return RiskCheckResult(approved=False, reasons=reasons)
        
        # 6. Check freeze quantity (for F&O)
        if signal.instrument.freeze_quantity:
            if position_size > signal.instrument.freeze_quantity:
                reasons.append(
                    f"Position size {position_size} exceeds freeze quantity {signal.instrument.freeze_quantity}"
                )
                # Reduce to freeze quantity
                position_size = signal.instrument.freeze_quantity
                logger.warning(
                    "Position size capped at freeze quantity",
                    instrument=signal.instrument.tradingsymbol,
                    size=position_size
                )
        
        # 7. Check available margin
        estimated_margin = self.estimate_margin_required(
            signal.instrument,
            position_size,
            signal.entry_price
        )
        
        if estimated_margin > portfolio_risk.available_margin:
            reasons.append(
                f"Insufficient margin: required {estimated_margin:.0f}, available {portfolio_risk.available_margin:.0f}"
            )
            return RiskCheckResult(approved=False, reasons=reasons)
        
        # All checks passed
        logger.info(
            "Risk check passed",
            instrument=signal.instrument.tradingsymbol,
            size=position_size,
            risk_pct=trade_risk_pct,
            new_heat_pct=new_heat_pct
        )
        
        return RiskCheckResult(
            approved=True,
            reasons=["All risk checks passed"],
            risk_pct=trade_risk_pct,
            position_size=position_size
        )
    
    def calculate_position_size(
        self,
        signal: Signal,
        net_liquid: float,
        instrument: Instrument
    ) -> int:
        """
        Calculate position size based on risk parameters.
        
        Formula:
        Position Size = (Capital * Risk%) / Stop Distance
        
        For F&O, round to lot sizes.
        
        Args:
            signal: Trading signal with entry and stop
            net_liquid: Net liquid capital
            instrument: Instrument details
        
        Returns:
            Position size in quantity (not lots)
        """
        if signal.stop_distance <= 0:
            logger.warning("Invalid stop distance", distance=signal.stop_distance)
            return 0
        
        # Calculate risk amount
        risk_amount = net_liquid * (self.config.per_trade_risk_pct / 100)
        
        # Calculate quantity
        quantity = risk_amount / signal.stop_distance
        
        # Apply max position size multiplier
        max_quantity = instrument.lot_size * self.config.max_position_size_multiplier
        quantity = min(quantity, max_quantity)
        
        # Round to lot size for F&O
        if instrument.lot_size > 1:
            lots = int(quantity / instrument.lot_size)
            lots = max(1, lots)  # At least 1 lot
            quantity = lots * instrument.lot_size
        else:
            # For equities, round down
            quantity = int(quantity)
        
        logger.debug(
            "Position size calculated",
            instrument=instrument.tradingsymbol,
            quantity=quantity,
            lots=quantity // instrument.lot_size if instrument.lot_size > 1 else quantity,
            risk_amount=risk_amount
        )
        
        return int(quantity)
    
    def estimate_margin_required(
        self,
        instrument: Instrument,
        quantity: int,
        price: float
    ) -> float:
        """
        Estimate margin required for a position.
        
        This is a simplified calculation. In production, use
        Kite's margin calculator API.
        
        Args:
            instrument: Instrument details
            quantity: Position quantity
            price: Entry price
        
        Returns:
            Estimated margin in INR
        """
        if instrument.is_equity:
            # CNC requires full capital
            return quantity * price
        
        elif instrument.is_future:
            # Futures require margin (approx 10-20% for indices, higher for stocks)
            # Use conservative 25%
            return quantity * price * 0.25
        
        elif instrument.is_option:
            # Options: Premium + SPAN + Exposure
            # For buying: Premium only
            # For selling: Premium + margin
            # Simplified: Premium * 5 for selling, Premium for buying
            return quantity * price * 5
        
        return quantity * price
    
    def estimate_fees(
        self,
        instrument: Instrument,
        quantity: int,
        entry_price: float,
        exit_price: float
    ) -> float:
        """
        Estimate trading fees for a round trip.
        
        Includes:
        - Brokerage
        - STT/CTT
        - Exchange charges
        - GST
        - SEBI charges
        - Stamp duty
        
        Args:
            instrument: Instrument details
            quantity: Position quantity
            entry_price: Entry price
            exit_price: Exit price
        
        Returns:
            Estimated total fees in INR
        """
        turnover = quantity * (entry_price + exit_price)
        
        # Simplified fee calculation (Zerodha-like structure)
        fees = 0.0
        
        # Brokerage: 0.03% of turnover or Rs 20 per order, whichever is lower (per side for equities)
        if instrument.is_equity:
            # Equity Intraday: 0.03% or Rs 20/executing order whichever is lower
            # Calculate per side to be accurate
            entry_brokerage = min(self.config.fees_per_order, entry_price * quantity * 0.0003)
            exit_brokerage = min(self.config.fees_per_order, exit_price * quantity * 0.0003)
            fees += entry_brokerage + exit_brokerage
        elif instrument.is_future or instrument.is_option:
            fees += self.config.fees_per_order * 2
            # Note: Unlike the previous implementation, fees_per_option_leg is not added here
            # as brokerage is usually flat per order for F&O. If multi-leg order costs are needed,
            # they should be modeled as multiple orders.
        # Tax Rates (2024-2025)
        # TODO: Move to config or constants
        STT_EQUITY_INTRADAY_SELL = 0.00025  # 0.025%
        STT_FUTURES_SELL = 0.000125         # 0.0125%
        STT_OPTIONS_SELL = 0.000625         # 0.0625% (on premium)
        
        TXN_NSE_EQUITY = 0.0000325          # 0.00325%
        TXN_NSE_FUTURES = 0.000019          # 0.0019%
        TXN_NSE_OPTIONS = 0.0005            # 0.05% (on premium)

        # Exchange Transaction Charges
        txn_charges = 0.0
        if instrument.exchange in ["NSE", "BSE", "NFO"]:
            if instrument.is_equity:
                txn_charges = turnover * TXN_NSE_EQUITY
            elif instrument.is_future:
                txn_charges = turnover * TXN_NSE_FUTURES
            elif instrument.is_option:
                txn_charges = turnover * TXN_NSE_OPTIONS
        else:
            txn_charges = turnover * 0.00002  # Default fallback
        
        fees += txn_charges

        # GST on brokerage and transaction charges: 18%
        # Note: GST is NOT applied on STT or Stamp Duty
        fees *= 1.18

        # STT Calculation
        stt = 0.0
        if instrument.is_equity:
            # Assuming Intraday for now as safe default. For delivery it's higher (0.1% on both sides).
            stt = (exit_price * quantity) * STT_EQUITY_INTRADAY_SELL
        elif instrument.is_future:
            stt = (exit_price * quantity) * STT_FUTURES_SELL
        elif instrument.is_option:
            stt = (exit_price * quantity) * STT_OPTIONS_SELL

        fees += stt
        
        # SEBI charges: Rs 10 per crore
        fees += (turnover / 10000000) * 10
        
        # Stamp duty: 0.003% on buy side
        fees += (entry_price * quantity) * 0.00003
        
        return fees
    
    def update_portfolio_risk(
        self,
        net_liquid: float,
        positions: List[Position],
        realized_pnl_today: float
    ) -> PortfolioRisk:
        """
        Calculate current portfolio risk metrics.
        
        Args:
            net_liquid: Net liquid capital
            positions: Open positions
            realized_pnl_today: Realized P&L today
        
        Returns:
            PortfolioRisk object
        """
        # Initialize daily capital if needed
        if self.daily_start_capital is None:
            self.daily_start_capital = net_liquid
        
        # Calculate total risk
        total_risk = sum([pos.risk_amount for pos in positions if pos.is_open])
        
        # Calculate unrealized PnL
        unrealized_pnl = sum([pos.unrealized_pnl for pos in positions if pos.is_open])
        
        # Calculate daily PnL
        daily_pnl = realized_pnl_today + unrealized_pnl
        
        # Calculate limits
        daily_loss_limit = -1 * self.daily_start_capital * (self.config.daily_loss_stop_pct / 100)
        max_portfolio_heat = self.daily_start_capital * (self.config.max_portfolio_heat_pct / 100)
        
        # Estimate used margin (simplified)
        used_margin = sum([
            self.estimate_margin_required(pos.instrument, pos.quantity, pos.entry_price)
            for pos in positions if pos.is_open
        ])
        
        available_margin = net_liquid - used_margin
        
        portfolio_risk = PortfolioRisk(
            net_liquid=net_liquid,
            used_margin=used_margin,
            available_margin=available_margin,
            open_positions=positions,
            total_risk_amount=total_risk,
            unrealized_pnl=unrealized_pnl,
            realized_pnl_today=realized_pnl_today,
            daily_pnl=daily_pnl,
            daily_loss_limit=daily_loss_limit,
            max_portfolio_heat=max_portfolio_heat
        )
        
        return portfolio_risk
    
    def reset_daily_counters(self) -> None:
        """Reset daily counters (call at start of day)"""
        self.daily_start_capital = None
        self.trades_today = 0
        logger.info("Daily risk counters reset")
    
    def can_enter(
        self,
        risk_cfg: RiskConfig,
        portfolio: PortfolioRisk,
        stop_dist: float,
        instrument: Instrument,
        price: float,
        capital: float
    ) -> tuple[bool, int]:
        """
        Hard gate check: can we enter this trade?
        
        Returns:
            (approved: bool, quantity: int)
        """
        # 1. Per-trade risk
        rupees_risk = capital * (risk_cfg.per_trade_risk_pct / 100)
        qty = max(1, int(rupees_risk / (stop_dist * instrument.lot_size * price) * instrument.lot_size))
        
        # Round to lot size
        if instrument.lot_size > 1:
            lots = max(1, int(qty / instrument.lot_size))
            qty = lots * instrument.lot_size
        
        # 2. Portfolio heat check
        open_risk = portfolio.total_risk_amount
        if (open_risk + rupees_risk) > capital * (risk_cfg.max_portfolio_heat_pct / 100):
            logger.warning("Portfolio heat limit would be breached",
                         current_heat=open_risk,
                         new_risk=rupees_risk,
                         limit=capital * (risk_cfg.max_portfolio_heat_pct / 100))
            return False, 0
        
        # 3. Daily loss stop
        if portfolio.realized_pnl_today <= -capital * (risk_cfg.daily_loss_stop_pct / 100):
            logger.warning("Daily loss stop breached",
                         daily_pnl=portfolio.realized_pnl_today,
                         limit=-capital * (risk_cfg.daily_loss_stop_pct / 100))
            return False, 0
        
        return True, qty
