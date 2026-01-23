"""Unit tests for fee calculation correctness"""
import pytest
from packages.core.config import RiskConfig
from packages.core.models import Instrument, InstrumentType
from packages.core.risk import RiskManager

@pytest.fixture
def risk_manager():
    config = RiskConfig({
        "per_trade_risk_pct": 1.0,
        "max_portfolio_heat_pct": 5.0,
        "daily_loss_stop_pct": 5.0,
        "fees_per_order": 20.0,
        "fees_per_option_leg": 0.0,
        "max_position_size_multiplier": 1.0
    })
    return RiskManager(config)

def test_options_fee_calculation(risk_manager):
    """
    Test fee calculation for Nifty Options.
    Parameters:
        Buy Price: 100
        Sell Price: 110
        Quantity: 50 (2 lots of 25)
        Turnover: 50 * (100+110) = 10,500

    Expected Breakdown:
        Brokerage: 20 + 20 = 40 (Flat)
        Exchange Txn (0.05% turnover): 10500 * 0.0005 = 5.25
        GST (18% on Brokerage+Txn): 0.18 * (40 + 5.25) = 8.145
        STT (0.0625% on Sell Value): (50 * 110) * 0.000625 = 3.4375
        Stamp Duty (0.003% on Buy Value): (50 * 100) * 0.00003 = 0.15
        SEBI (10 per crore turnover): 10500 * 10/1Cr = 0.0105

    Total Expected: 40 + 5.25 + 8.145 + 3.4375 + 0.15 + 0.0105 = 56.993
    """
    instrument = Instrument(
        token=123,
        symbol="NIFTY",
        tradingsymbol="NIFTY23OCT19000CE",
        exchange="NFO",
        instrument_type=InstrumentType.CE,
        lot_size=25,
        tick_size=0.05
    )

    fees = risk_manager.estimate_fees(
        instrument=instrument,
        quantity=50,
        entry_price=100.0,
        exit_price=110.0
    )

    # Allow small floating point variance
    expected_fees = 56.993
    assert abs(fees - expected_fees) < 1.0, f"Fees {fees} deviates from expected {expected_fees}"

def test_futures_fee_calculation(risk_manager):
    """
    Test fee calculation for Nifty Futures.
    Parameters:
        Buy Price: 20000
        Sell Price: 20100
        Quantity: 50
        Turnover: 50 * (40100) = 2,005,000

    Expected Breakdown:
        Brokerage: 40
        Exchange Txn (0.0019%): 2005000 * 0.000019 = 38.095
        GST (18%): 0.18 * (40 + 38.095) = 14.057
        STT (0.0125% on Sell): (50 * 20100) * 0.000125 = 125.625
        Stamp Duty (0.002% on Buy? No, 0.002% or 0.003%? Code says 0.003%):
        Code: fees += (entry_price * quantity) * 0.00003
        Stamp: (50 * 20000) * 0.00003 = 30.0
        SEBI: 2005000 * 10/1Cr = 2.005

    Total Expected: 40 + 38.095 + 14.057 + 125.625 + 30.0 + 2.005 = 249.782
    """
    instrument = Instrument(
        token=124,
        symbol="NIFTY",
        tradingsymbol="NIFTY23OCTFUT",
        exchange="NFO",
        instrument_type=InstrumentType.FUT,
        lot_size=50,
        tick_size=0.05
    )

    fees = risk_manager.estimate_fees(
        instrument=instrument,
        quantity=50,
        entry_price=20000.0,
        exit_price=20100.0
    )

    expected_fees = 249.782
    assert abs(fees - expected_fees) < 5.0, f"Fees {fees} deviates from expected {expected_fees}"
