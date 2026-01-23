"""Unit tests for risk management"""
import pytest
from datetime import datetime

from packages.core.config import RiskConfig
from packages.core.models import Instrument, InstrumentType, Signal, SignalSide
from packages.core.risk import PortfolioRisk, RiskManager


@pytest.fixture
def risk_config():
    """Create risk config for testing"""
    return RiskConfig({
        "per_trade_risk_pct": 0.5,
        "max_portfolio_heat_pct": 2.0,
        "daily_loss_stop_pct": 2.5,
        "slippage_bps": 5,
        "fees_per_order": 20,
        "fees_per_option_leg": 2,
        "max_position_size_multiplier": 3
    })


@pytest.fixture
def risk_manager(risk_config):
    """Create risk manager for testing"""
    return RiskManager(risk_config)


@pytest.fixture
def sample_instrument():
    """Create sample instrument"""
    return Instrument(
        token=256265,
        symbol="NIFTY",
        tradingsymbol="NIFTY25DEC24FUT",
        exchange="NFO",
        instrument_type=InstrumentType.FUT,
        lot_size=50,
        tick_size=0.05
    )


@pytest.fixture
def sample_signal(sample_instrument):
    """Create sample trading signal"""
    return Signal(
        strategy_name="TestStrategy",
        timestamp=datetime.now(),
        instrument=sample_instrument,
        side=SignalSide.LONG,
        entry_price=22000.0,
        stop_loss=21900.0,  # 100 points risk
        take_profit_1=22150.0,
        take_profit_2=22300.0,
        confidence=0.75
    )


def test_position_sizing_basic(risk_manager, sample_signal, sample_instrument):
    """Test basic position sizing calculation"""
    net_liquid = 1000000  # 10 lakh
    
    # Expected: (1000000 * 0.5%) / 100 = 50 quantity
    # With lot size 50, should be 1 lot = 50
    position_size = risk_manager.calculate_position_size(
        signal=sample_signal,
        net_liquid=net_liquid,
        instrument=sample_instrument
    )
    
    assert position_size == 50
    assert position_size % sample_instrument.lot_size == 0


def test_position_sizing_lot_multiples(risk_manager, sample_signal, sample_instrument):
    """Test position sizing respects lot sizes"""
    net_liquid = 5000000  # 50 lakh
    
    position_size = risk_manager.calculate_position_size(
        signal=sample_signal,
        net_liquid=net_liquid,
        instrument=sample_instrument
    )
    
    # Should be multiple of lot size
    assert position_size % sample_instrument.lot_size == 0
    
    # Should not exceed max multiplier (3 lots)
    assert position_size <= sample_instrument.lot_size * 3


def test_risk_check_passes(risk_manager, sample_signal):
    """Test risk check passes with valid conditions"""
    portfolio_risk = PortfolioRisk(
        net_liquid=1000000,
        used_margin=100000,
        available_margin=900000,
        open_positions=[],
        total_risk_amount=0,
        unrealized_pnl=0,
        realized_pnl_today=0,
        daily_pnl=0,
        daily_loss_limit=-25000,
        max_portfolio_heat=20000
    )
    
    result = risk_manager.check_signal(sample_signal, portfolio_risk)
    
    assert result.approved is True
    assert result.position_size > 0


def test_risk_check_daily_loss_breach(risk_manager, sample_signal):
    """Test risk check fails when daily loss limit breached"""
    portfolio_risk = PortfolioRisk(
        net_liquid=1000000,
        used_margin=0,
        available_margin=1000000,
        open_positions=[],
        total_risk_amount=0,
        unrealized_pnl=0,
        realized_pnl_today=-30000,
        daily_pnl=-30000,  # -3% loss (exceeds -2.5% limit)
        daily_loss_limit=-25000,
        max_portfolio_heat=20000
    )
    
    result = risk_manager.check_signal(sample_signal, portfolio_risk)
    
    assert result.approved is False
    assert "Daily loss limit breached" in result.reasons[0]


def test_risk_check_portfolio_heat_breach(risk_manager, sample_signal):
    """Test risk check fails when portfolio heat limit breached"""
    portfolio_risk = PortfolioRisk(
        net_liquid=1000000,
        used_margin=100000,
        available_margin=900000,
        open_positions=[],
        total_risk_amount=25000,  # Already at 2.5% heat
        unrealized_pnl=0,
        realized_pnl_today=0,
        daily_pnl=0,
        daily_loss_limit=-25000,
        max_portfolio_heat=20000  # Max 2% heat
    )
    
    result = risk_manager.check_signal(sample_signal, portfolio_risk)
    
    assert result.approved is False
    assert "Portfolio heat limit breached" in result.reasons[0]


def test_fee_estimation(risk_manager, sample_instrument):
    """Test fee calculation"""
    quantity = 50
    entry_price = 22000.0
    exit_price = 22200.0
    
    fees = risk_manager.estimate_fees(
        instrument=sample_instrument,
        quantity=quantity,
        entry_price=entry_price,
        exit_price=exit_price
    )
    
    assert fees > 0
    assert fees < 1000  # Reasonable fee range


def test_margin_estimation(risk_manager, sample_instrument):
    """Test margin estimation"""
    quantity = 50
    price = 22000.0
    
    margin = risk_manager.estimate_margin_required(
        instrument=sample_instrument,
        quantity=quantity,
        price=price
    )
    
    # For futures, should be roughly 25% of notional
    notional = quantity * price
    assert margin > 0
    assert margin < notional  # Less than full notional
    assert margin > notional * 0.1  # More than 10% (conservative)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

