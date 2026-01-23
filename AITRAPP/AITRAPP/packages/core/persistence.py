"""Persistence helpers for orchestrator"""
import hashlib
from datetime import datetime
from typing import Optional
import structlog

from packages.storage.models import (
    Signal, Decision, Order, OrderStatusEnum, OrderTypeEnum, OrderSideEnum,
    DecisionStatusEnum, SideEnum
)
from packages.storage.database import get_db_session
from packages.core.models import Signal as CoreSignal
from packages.core.config import app_config

logger = structlog.get_logger(__name__)


def get_config_sha() -> str:
    """Get SHA256 hash of current config for reproducibility"""
    config_str = str(app_config.dict())
    return hashlib.sha256(config_str.encode()).hexdigest()[:16]


def persist_signal(
    signal: CoreSignal,
    score: Optional[float] = None,
    rank: Optional[int] = None,
    features: Optional[dict] = None,
    feature_scores: Optional[dict] = None,
    penalties: Optional[dict] = None
) -> Signal:
    """Persist a signal to database"""
    with get_db_session() as db:
        signal_model = Signal(
            ts=datetime.utcnow(),
            symbol=signal.instrument.symbol,
            instrument_token=signal.instrument.token,
            side=SideEnum.LONG if signal.side.value == "LONG" else SideEnum.SHORT,
            strategy=signal.strategy_name,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit_1=signal.take_profit_1,
            take_profit_2=signal.take_profit_2,
            score=score,
            rank=rank,
            confidence=signal.confidence,
            features=features or {},
            feature_scores=feature_scores or {},
            penalties=penalties or {},
            rationale=signal.rationale,
            config_sha=get_config_sha()
        )
        db.add(signal_model)
        db.commit()
        db.refresh(signal_model)
        
        logger.debug("Signal persisted", signal_id=signal_model.id, strategy=signal.strategy_name)
        return signal_model


def persist_decision(
    signal_model: Signal,
    approved: bool,
    risk_pct: float,
    risk_amount: float,
    position_size: int,
    rr_expected: Optional[float] = None,
    portfolio_heat_before: Optional[float] = None,
    portfolio_heat_after: Optional[float] = None,
    rejection_reasons: Optional[list] = None
) -> Decision:
    """Persist a decision to database"""
    with get_db_session() as db:
        # Generate deterministic client_plan_id
        client_plan_id = f"PLAN_{signal_model.id}_{datetime.utcnow().isoformat()}"
        
        decision_model = Decision(
            ts=datetime.utcnow(),
            signal_id=signal_model.id,
            client_plan_id=client_plan_id,
            mode=app_config.mode,
            status=DecisionStatusEnum.PLANNED if approved else DecisionStatusEnum.REJECTED,
            risk_perc=risk_pct,
            risk_amount=risk_amount,
            rr_expected=rr_expected,
            position_size=position_size,
            portfolio_heat_before=portfolio_heat_before,
            portfolio_heat_after=portfolio_heat_after,
            rejection_reasons=rejection_reasons or []
        )
        db.add(decision_model)
        db.commit()
        db.refresh(decision_model)
        
        logger.debug("Decision persisted", 
                    decision_id=decision_model.id,
                    approved=approved,
                    client_plan_id=client_plan_id)
        return decision_model


def persist_order(
    decision_model: Decision,
    symbol: str,
    instrument_token: int,
    side: str,  # "BUY" or "SELL"
    qty: int,
    order_type: str,  # "MARKET", "LIMIT", "SL", "SL-M"
    price: Optional[float] = None,
    trigger_price: Optional[float] = None,
    tag: str = "ENTRY",
    parent_group: Optional[str] = None,
    broker_order_id: Optional[str] = None,
    strategy_name: Optional[str] = None
) -> Order:
    """Persist an order to database"""
    with get_db_session() as db:
        # Generate deterministic client_order_id
        client_order_id = f"{decision_model.client_plan_id}_{tag}_{datetime.utcnow().timestamp()}"
        
        order_model = Order(
            ts=datetime.utcnow(),
            decision_id=decision_model.id,
            client_order_id=client_order_id,
            broker_order_id=broker_order_id,
            symbol=symbol,
            instrument_token=instrument_token,
            side=OrderSideEnum.BUY if side == "BUY" else OrderSideEnum.SELL,
            qty=qty,
            order_type=OrderTypeEnum(order_type),
            price=price,
            trigger_price=trigger_price,
            tag=tag,
            parent_group=parent_group,
            is_stop_loss=(tag == "STOP"),
            is_take_profit=(tag in ["TP1", "TP2"]),
            strategy_name=strategy_name or decision_model.signal.strategy,
            status=OrderStatusEnum.PLACED if broker_order_id else OrderStatusEnum.PLACED
        )
        db.add(order_model)
        db.commit()
        db.refresh(order_model)
        
        logger.debug("Order persisted", 
                    order_id=order_model.id,
                    client_order_id=client_order_id,
                    tag=tag)
        return order_model


def update_order_status(
    client_order_id: str,
    broker_order_id: Optional[str] = None,
    status: Optional[OrderStatusEnum] = None,
    filled_qty: Optional[int] = None,
    average_price: Optional[float] = None
) -> Optional[Order]:
    """Update order status"""
    with get_db_session() as db:
        order = db.query(Order).filter_by(client_order_id=client_order_id).first()
        if not order:
            logger.warning("Order not found for update", client_order_id=client_order_id)
            return None
        
        if broker_order_id:
            order.broker_order_id = broker_order_id
        if status:
            order.status = status
        if filled_qty is not None:
            order.filled_qty = filled_qty
        if average_price is not None:
            order.average_price = average_price
        
        db.commit()
        db.refresh(order)
        
        logger.debug("Order updated", 
                    client_order_id=client_order_id,
                    status=status.value if status else None)
        return order

