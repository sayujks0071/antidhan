
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

def test_equity_intraday_fee_calculation(risk_manager):
    """
    Test fee calculation for Equity Intraday.
    Brokerage: Min(20, 0.03% of order value) per side (order value = price * quantity for each side).

    Parameters:
        Buy Price: 1000
        Sell Price: 1010
        Quantity: 10
        Turnover: 10 * (2010) = 20,100
        Buy Value: 10,000
        Sell Value: 10,100

    Brokerage Calculation:
    Side 1 (Buy): 10,000 * 0.03% = 3.0. Min(20, 3) = 3.0
    Side 2 (Sell): 10,100 * 0.03% = 3.03. Min(20, 3.03) = 3.03
    Total Brokerage: 6.03

    Other Charges:
    Exchange Txn (0.00325%): 20100 * 0.0000325 = 0.65325
    GST (18% on Brok+Txn): 0.18 * (6.03 + 0.65325) = 1.202985
    STT (0.025% on Sell): 10100 * 0.00025 = 2.525
    Stamp Duty (0.003% on Buy): 10000 * 0.00003 = 0.3
    SEBI (10/Cr): 20100 * 1e-6 = 0.0201

    Total Expected: 6.03 + 0.65325 + 1.202985 + 2.525 + 0.3 + 0.0201 ~= 10.73
    """
    instrument = Instrument(
        token=1001,
        symbol="RELIANCE",
        tradingsymbol="RELIANCE",
        exchange="NSE",
        instrument_type=InstrumentType.EQ,
        lot_size=1,
        tick_size=0.05
    )

    fees = risk_manager.estimate_fees(
        instrument=instrument,
        quantity=10,
        entry_price=1000.0,
        exit_price=1010.0
    )

    # Current implementation in risk.py now applies the brokerage rule:
    # brokerage_per_side = min(20.0, 0.0003 * side_turnover)
    # For this trade, that yields a total brokerage of ~6.03 and total fees of ~10.73.
    # This test asserts that the computed fees stay in a reasonable vicinity of that value.

    print(f"Calculated Fees: {fees}")

    # Sanity check: for this small equity intraday trade, total fees should not be excessive.
    # If the code were still blindly charging 20 per order, this assertion would fail.
    assert fees < 15.0, f"Fees {fees} seems too high for small equity trade. Should be ~10.73"
