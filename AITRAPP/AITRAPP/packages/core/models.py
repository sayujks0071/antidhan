"""Core trading models and data structures"""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class InstrumentType(str, Enum):
    """Instrument types"""
    EQ = "EQ"  # Equity
    FUT = "FUT"  # Futures
    CE = "CE"  # Call Option
    PE = "PE"  # Put Option


class SignalSide(str, Enum):
    """Signal direction"""
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


class OrderStatus(str, Enum):
    """Order status"""
    PENDING = "PENDING"
    OPEN = "OPEN"
    COMPLETE = "COMPLETE"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    TRIGGERED = "TRIGGERED"


class PositionStatus(str, Enum):
    """Position status"""
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    PARTIAL = "PARTIAL"


@dataclass
class Instrument:
    """Instrument details"""
    token: int
    symbol: str
    tradingsymbol: str
    exchange: str
    instrument_type: InstrumentType
    expiry: Optional[datetime] = None
    strike: Optional[float] = None
    lot_size: int = 1
    tick_size: float = 0.05
    freeze_quantity: Optional[int] = None

    # Metadata
    segment: Optional[str] = None
    isin: Optional[str] = None

    @property
    def is_option(self) -> bool:
        return self.instrument_type in (InstrumentType.CE, InstrumentType.PE)

    @property
    def is_future(self) -> bool:
        return self.instrument_type == InstrumentType.FUT

    @property
    def is_equity(self) -> bool:
        return self.instrument_type == InstrumentType.EQ


@dataclass
class Tick:
    """Market tick data"""
    token: int
    timestamp: datetime
    last_price: float
    last_quantity: int = 0
    volume: int = 0
    bid: float = 0.0
    ask: float = 0.0
    bid_quantity: int = 0
    ask_quantity: int = 0
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    oi: int = 0
    oi_day_high: int = 0
    oi_day_low: int = 0

    @property
    def mid(self) -> float:
        """Mid price between bid and ask"""
        if self.bid > 0 and self.ask > 0:
            return (self.bid + self.ask) / 2
        return self.last_price

    @property
    def spread(self) -> float:
        """Bid-ask spread"""
        return self.ask - self.bid

    @property
    def spread_pct(self) -> float:
        """Spread as percentage of mid"""
        mid = self.mid
        if mid > 0:
            return (self.spread / mid) * 100
        return 0.0


@dataclass
class TechnicalIndicators:
    """Technical indicators container"""
    vwap: Optional[float] = None
    atr: Optional[float] = None
    rsi: Optional[float] = None
    adx: Optional[float] = None
    ema_fast: Optional[float] = None
    ema_slow: Optional[float] = None
    supertrend: Optional[float] = None
    supertrend_direction: Optional[int] = None
    bb_upper: Optional[float] = None
    bb_middle: Optional[float] = None
    bb_lower: Optional[float] = None
    dc_upper: Optional[float] = None
    dc_lower: Optional[float] = None
    obv: Optional[float] = None
    historical_volatility: Optional[float] = None
    iv_rank: Optional[float] = None


@dataclass
class Bar:
    """Aggregated bar data"""
    token: int
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    oi: Optional[int] = None

    # Technical indicators (computed)
    # Note: These are attached dynamically in some flows, but defining them here or using TechnicalIndicators is better
    vwap: Optional[float] = None
    atr: Optional[float] = None
    rsi: Optional[float] = None
    adx: Optional[float] = None
    ema_fast: Optional[float] = None
    ema_slow: Optional[float] = None
    supertrend: Optional[float] = None
    supertrend_direction: Optional[int] = None

    @property
    def typical_price(self) -> float:
        """Typical price: (H + L + C) / 3"""
        return (self.high + self.low + self.close) / 3


@dataclass
class Signal:
    """Trading signal"""
    strategy_name: str
    timestamp: datetime
    instrument: Instrument
    side: SignalSide
    entry_price: float
    stop_loss: float
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None

    # Metadata
    confidence: float = 0.0  # 0-1
    rationale: str = ""
    features: Dict[str, Any] = field(default_factory=dict)

    # Risk-Reward
    risk_amount: float = 0.0
    reward_amount: float = 0.0

    @property
    def risk_reward_ratio(self) -> float:
        """Risk-reward ratio"""
        if self.risk_amount > 0:
            return self.reward_amount / self.risk_amount
        return 0.0

    @property
    def stop_distance(self) -> float:
        """Distance from entry to stop"""
        return abs(self.entry_price - self.stop_loss)


@dataclass
class RankedOpportunity:
    """Ranked trading opportunity"""
    signal: Signal
    score: float
    rank: int

    # Feature contributions
    feature_scores: Dict[str, float] = field(default_factory=dict)
    penalties_applied: Dict[str, float] = field(default_factory=dict)

    # Liquidity metrics
    liquidity_score: float = 0.0
    avg_volume: int = 0

    # Regime
    regime_score: float = 0.0
    iv_percentile: Optional[float] = None


@dataclass
class RankedCandidate:
    """Ranked candidate signal (internal to ranking engine)"""
    signal: Signal
    score: Decimal
    rank: int
    feature_scores: Dict[str, Decimal]
    penalties: Dict[str, Decimal]
    market_regime: str
    liquidity_score: Decimal
    timestamp: datetime


@dataclass
class Order:
    """Order details"""
    order_id: str
    client_order_id: str
    timestamp: datetime
    instrument: Instrument
    side: str  # BUY or SELL
    quantity: int
    price: float
    order_type: str
    product: str
    status: OrderStatus
    filled_quantity: int = 0
    average_price: float = 0.0

    # Parent-child relationships for OCO
    parent_order_id: Optional[str] = None
    is_stop_loss: bool = False
    is_take_profit: bool = False

    # Metadata
    strategy_name: Optional[str] = None
    signal_id: Optional[str] = None

    @property
    def is_filled(self) -> bool:
        return self.status == OrderStatus.COMPLETE

    @property
    def is_active(self) -> bool:
        return self.status in (OrderStatus.PENDING, OrderStatus.OPEN, OrderStatus.TRIGGERED)


@dataclass
class Position:
    """Position details"""
    position_id: str
    instrument: Instrument
    entry_time: datetime
    entry_price: float
    quantity: int
    side: SignalSide

    # Current state
    current_price: float
    unrealized_pnl: float = 0.0

    # Exit levels
    stop_loss: float = 0.0
    trailing_stop: Optional[float] = None
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None

    # Risk metrics
    risk_amount: float = 0.0
    max_favorable_excursion: float = 0.0  # MFE
    max_adverse_excursion: float = 0.0  # MAE

    # Status
    status: PositionStatus = PositionStatus.OPEN
    close_time: Optional[datetime] = None
    close_price: Optional[float] = None
    realized_pnl: Optional[float] = None

    # Metadata
    strategy_name: str = ""
    signal_id: Optional[str] = None
    entry_order_id: Optional[str] = None
    exit_order_id: Optional[str] = None

    def update_pnl(self):
        """Update unrealized PnL and MFE/MAE"""
        if self.side == SignalSide.LONG:
            self.unrealized_pnl = (self.current_price - self.entry_price) * self.quantity
        else:
            self.unrealized_pnl = (self.entry_price - self.current_price) * self.quantity

        # Update MFE/MAE
        if self.unrealized_pnl > self.max_favorable_excursion:
            self.max_favorable_excursion = self.unrealized_pnl
        if self.unrealized_pnl < self.max_adverse_excursion:
            self.max_adverse_excursion = self.unrealized_pnl

    @property
    def is_open(self) -> bool:
        return self.status == PositionStatus.OPEN

    @property
    def pnl_pct(self) -> float:
        """PnL as percentage of entry"""
        cost = self.entry_price * self.quantity
        if cost > 0:
            return (self.unrealized_pnl / cost) * 100
        return 0.0


@dataclass
class Trade:
    """Completed trade record"""
    trade_id: str
    instrument: Instrument
    strategy_name: str

    # Entry
    entry_time: datetime
    entry_price: float
    entry_order_id: str

    # Exit
    exit_time: datetime
    exit_price: float
    exit_order_id: str
    exit_reason: str

    # Trade details
    quantity: int
    side: SignalSide

    # P&L
    gross_pnl: float
    fees: float
    net_pnl: float
    pnl_pct: float

    # Risk metrics
    risk_amount: float
    rr_actual: float
    mfe: float
    mae: float

    # Duration
    duration_seconds: int

    # Metadata
    signal_id: Optional[str] = None
    config_sha: Optional[str] = None


class PortfolioState(BaseModel):
    """Current portfolio state"""
    timestamp: datetime
    net_liquid: float
    used_margin: float
    available_margin: float

    # Positions
    open_positions: List[Position] = Field(default_factory=list)
    total_positions: int = 0

    # P&L
    unrealized_pnl: float = 0.0
    realized_pnl_today: float = 0.0
    daily_pnl: float = 0.0
    daily_pnl_pct: float = 0.0

    # Risk metrics
    portfolio_heat: float = 0.0  # Total risk as % of capital
    portfolio_heat_pct: float = 0.0

    # Limits
    max_portfolio_heat_pct: float = 2.0
    daily_loss_limit: float = 0.0

    @property
    def is_daily_loss_breached(self) -> bool:
        return self.daily_pnl < self.daily_loss_limit

    @property
    def is_heat_limit_breached(self) -> bool:
        return self.portfolio_heat_pct >= self.max_portfolio_heat_pct

    @property
    def can_take_new_position(self) -> bool:
        return not (self.is_daily_loss_breached or self.is_heat_limit_breached)


class SystemState(BaseModel):
    """Overall system state"""
    timestamp: datetime
    mode: str  # PAPER or LIVE
    is_paused: bool = False
    is_market_open: bool = False

    # Portfolio
    portfolio: PortfolioState

    # Pending signals
    pending_signals: int = 0

    # Active orders
    active_orders: int = 0

    # Statistics
    trades_today: int = 0
    wins_today: int = 0
    losses_today: int = 0

    @property
    def win_rate(self) -> float:
        if self.trades_today > 0:
            return (self.wins_today / self.trades_today) * 100
        return 0.0


class RiskCheckResult(BaseModel):
    """Result of risk check"""
    approved: bool
    reasons: List[str] = Field(default_factory=list)
    risk_pct: float = 0.0
    position_size: int = 0
