"""SQLAlchemy ORM models for persistence"""
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from packages.storage.database import Base


class SideEnum(PyEnum):
    """Position/Order side"""
    LONG = "LONG"
    SHORT = "SHORT"
    BUY = "BUY"
    SELL = "SELL"


class OrderSideEnum(PyEnum):
    """Order side"""
    BUY = "BUY"
    SELL = "SELL"


class OrderTypeEnum(PyEnum):
    """Order type"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"
    SLM = "SL-M"


class OrderStatusEnum(PyEnum):
    """Order status"""
    PLACED = "PLACED"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class DecisionStatusEnum(PyEnum):
    """Decision status"""
    PLANNED = "PLANNED"
    SENT = "SENT"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class PositionStatusEnum(PyEnum):
    """Position status"""
    OPEN = "OPEN"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"


class TradeActionEnum(PyEnum):
    """Trade action"""
    OPEN = "OPEN"
    PARTIAL_EXIT = "PARTIAL_EXIT"
    FULL_EXIT = "FULL_EXIT"
    REVERSAL = "REVERSAL"


class AuditActionEnum(PyEnum):
    """Audit log action types"""
    KILL_SWITCH = "KILL_SWITCH"
    CONFIG_FROZEN = "CONFIG_FROZEN"
    MODE_CHANGE = "MODE_CHANGE"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    FLATTEN = "FLATTEN"
    RISK_BLOCK = "RISK_BLOCK"
    ORDER_PLACED = "ORDER_PLACED"
    ORDER_FILLED = "ORDER_FILLED"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    POSITION_OPENED = "POSITION_OPENED"
    POSITION_CLOSED = "POSITION_CLOSED"


class Instrument(Base):
    """Cached instrument data from Kite"""
    __tablename__ = "instruments"

    id = Column(Integer, primary_key=True)
    symbol = Column(String, index=True, nullable=False)
    exchange = Column(String, default="NSE", index=True)
    token = Column(BigInteger, index=True, nullable=False)  # Kite instrument_token
    tradingsymbol = Column(String, index=True)

    # Instrument properties
    lot_size = Column(Integer, default=1)
    tick_size = Column(Float, default=0.05)
    freeze_qty = Column(Integer, default=0)

    # Classification
    segment = Column(String)  # NFO|NSE|BSE
    kind = Column(String)     # FUT|OPT|EQ|IDX
    expiry = Column(String, nullable=True)
    strike = Column(Float, nullable=True)
    option_type = Column(String, nullable=True)  # CE|PE

    # Metadata
    isin = Column(String, nullable=True)
    last_synced = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('exchange', 'token', name='uix_ex_token'),
    )


class Signal(Base):
    """Generated trading signals"""
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True)
    ts = Column(DateTime, default=datetime.utcnow, index=True)

    # Signal details
    symbol = Column(String, index=True, nullable=False)
    instrument_token = Column(BigInteger, index=True)
    side = Column(Enum(SideEnum), nullable=False)
    strategy = Column(String, index=True, nullable=False)

    # Pricing
    entry_price = Column(Float)
    stop_loss = Column(Float)
    take_profit_1 = Column(Float, nullable=True)
    take_profit_2 = Column(Float, nullable=True)

    # Ranking
    score = Column(Float, nullable=True)
    rank = Column(Integer, nullable=True)
    confidence = Column(Float, default=0.0)

    # Features and attribution
    features = Column(JSON)  # Normalized feature vector
    feature_scores = Column(JSON)  # Individual feature contributions
    penalties = Column(JSON)  # Applied penalties

    # Metadata
    rationale = Column(String)
    config_sha = Column(String, index=True)  # Config version for reproducibility

    # Relationships
    decisions = relationship("Decision", back_populates="signal")


class Decision(Base):
    """Risk-checked decision to execute a signal"""
    __tablename__ = "decisions"

    id = Column(Integer, primary_key=True)
    ts = Column(DateTime, default=datetime.utcnow, index=True)

    # Links
    signal_id = Column(Integer, ForeignKey("signals.id"), index=True)
    client_plan_id = Column(String, index=True, unique=True)  # Deterministic, for idempotency

    # Execution details
    mode = Column(Enum("PAPER", "LIVE", name="mode"), nullable=False)
    status = Column(Enum(DecisionStatusEnum), default=DecisionStatusEnum.PLANNED)

    # Risk metrics
    risk_perc = Column(Float)  # Per-trade risk percentage
    risk_amount = Column(Float)  # Absolute risk in rupees
    rr_expected = Column(Float)  # Expected risk-reward ratio
    position_size = Column(Integer)  # Calculated quantity

    # Portfolio impact
    portfolio_heat_before = Column(Float)  # Heat before this decision
    portfolio_heat_after = Column(Float)  # Heat after this decision

    # Details
    details = Column(JSON)  # Additional decision metadata
    rejection_reasons = Column(JSON, nullable=True)  # If rejected

    # Relationships
    signal = relationship("Signal", back_populates="decisions")
    orders = relationship("Order", back_populates="decision")


class Order(Base):
    """Order records (broker orders)"""
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    ts = Column(DateTime, default=datetime.utcnow, index=True)

    # Links
    decision_id = Column(Integer, ForeignKey("decisions.id"), index=True, nullable=True)
    client_order_id = Column(String, index=True, unique=True)  # Idempotent
    broker_order_id = Column(String, index=True, nullable=True)  # Kite order_id

    # Order details
    symbol = Column(String, index=True, nullable=False)
    instrument_token = Column(BigInteger, index=True)
    side = Column(Enum(OrderSideEnum), nullable=False)
    qty = Column(Integer, nullable=False)
    order_type = Column(Enum(OrderTypeEnum), nullable=False)
    product = Column(String, default="MIS")

    # Pricing
    price = Column(Float, nullable=True)
    trigger_price = Column(Float, nullable=True)  # For SL orders
    average_price = Column(Float, nullable=True)  # Fill price
    filled_qty = Column(Integer, default=0)

    # Status
    status = Column(Enum(OrderStatusEnum), default=OrderStatusEnum.PLACED, index=True)

    # OCO management
    tag = Column(String, index=True)  # ENTRY|STOP|TP1|TP2
    parent_group = Column(String, index=True)  # OCO group UUID
    is_stop_loss = Column(Boolean, default=False)
    is_take_profit = Column(Boolean, default=False)

    # Metadata
    strategy_name = Column(String, index=True)
    meta = Column(JSON)  # Additional order metadata

    # Relationships
    decision = relationship("Decision", back_populates="orders")


class Position(Base):
    """Open positions"""
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True)
    position_id = Column(String, unique=True, index=True)  # Our internal ID

    # Position details
    symbol = Column(String, index=True, nullable=False)
    instrument_token = Column(BigInteger, index=True)
    side = Column(Enum(SideEnum), nullable=False)
    qty = Column(Integer, nullable=False)
    avg_price = Column(Float, nullable=False)

    # Current state
    current_price = Column(Float, default=0.0)
    unrealized = Column(Float, default=0.0)
    realized = Column(Float, default=0.0)

    # Exit levels
    stop_loss = Column(Float)
    trailing_stop = Column(Float, nullable=True)
    take_profit_1 = Column(Float, nullable=True)
    take_profit_2 = Column(Float, nullable=True)

    # Risk metrics
    risk_amount = Column(Float)
    mfe = Column(Float, default=0.0)  # Max favorable excursion
    mae = Column(Float, default=0.0)  # Max adverse excursion

    # OCO group
    oco_group = Column(String, index=True)

    # Lifecycle
    opened_at = Column(DateTime, default=datetime.utcnow, index=True)
    closed_at = Column(DateTime, nullable=True, index=True)
    status = Column(Enum(PositionStatusEnum), default=PositionStatusEnum.OPEN, index=True)

    # Metadata
    strategy_name = Column(String, index=True)
    entry_order_id = Column(String, nullable=True)
    exit_order_id = Column(String, nullable=True)
    exit_reason = Column(String, nullable=True)

    # Relationships
    trades = relationship("Trade", back_populates="position")


class Trade(Base):
    """Completed trades (entry + exit)"""
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True)
    position_id = Column(Integer, ForeignKey("positions.id"), index=True)
    ts = Column(DateTime, default=datetime.utcnow, index=True)

    # Trade details
    action = Column(Enum(TradeActionEnum), nullable=False)
    qty = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)

    # P&L
    fees = Column(Float, default=0.0)
    gross_pnl = Column(Float, default=0.0)
    net_pnl = Column(Float, default=0.0)
    pnl_pct = Column(Float, default=0.0)

    # Risk metrics
    risk_amount = Column(Float)
    rr_actual = Column(Float, nullable=True)

    # Relationships
    position = relationship("Position", back_populates="trades")


class RiskEvent(Base):
    """Risk limit breaches and events"""
    __tablename__ = "risk_events"

    id = Column(Integer, primary_key=True)
    ts = Column(DateTime, default=datetime.utcnow, index=True)

    # Event details
    event_type = Column(String, index=True)  # HEAT_LIMIT|DAILY_LOSS|PER_TRADE|FREEZE_QTY
    severity = Column(String)  # WARNING|CRITICAL|BLOCKED
    message = Column(String)

    # Context
    portfolio_heat = Column(Float, nullable=True)
    daily_pnl = Column(Float, nullable=True)
    per_trade_risk = Column(Float, nullable=True)

    # Action taken
    action = Column(String)  # BLOCKED|PAUSED|FLATTENED
    details = Column(JSON)


class AuditLog(Base):
    """Comprehensive audit trail"""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    ts = Column(DateTime, default=datetime.utcnow, index=True)

    # Log details
    action = Column(Enum(AuditActionEnum), index=True, nullable=True)  # Audit action type
    level = Column(String, index=True)  # INFO|WARN|ERROR|CRITICAL
    category = Column(String, index=True)  # SIGNAL|RISK|EXEC|EXIT|WS|API|ORCH
    message = Column(String, nullable=False)

    # Context
    correlation_id = Column(String, index=True)  # For tracing requests
    config_sha = Column(String, index=True)  # Config version

    # Data
    details = Column(JSON)  # Structured log data (renamed from 'data' for consistency)
    data = Column(JSON)  # Keep for backward compatibility

    # Links
    signal_id = Column(Integer, ForeignKey("signals.id"), nullable=True)
    decision_id = Column(Integer, ForeignKey("decisions.id"), nullable=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    position_id = Column(Integer, ForeignKey("positions.id"), nullable=True)

