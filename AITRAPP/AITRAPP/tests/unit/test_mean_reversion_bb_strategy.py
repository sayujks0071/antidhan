from datetime import datetime, timedelta

import pytest

from packages.core.models import Bar, Instrument, InstrumentType, SignalSide, Tick
from packages.core.strategies.base import StrategyContext
from packages.core.strategies.mean_reversion_bb import MeanReversionBBStrategy


@pytest.fixture
def bb_strategy():
    return MeanReversionBBStrategy("BB_Strat", {"period": 20, "std_dev": 2.0})

@pytest.fixture
def mock_context():
    instrument = Instrument(
        token=123,
        symbol="NIFTY",
        tradingsymbol="NIFTY25SEP",
        exchange="NSE",
        instrument_type=InstrumentType.EQ,
        strike=0,
        lot_size=1,
        tick_size=0.05
    )
    return StrategyContext(
        timestamp=datetime(2025, 10, 3, 9, 15),
        instrument=instrument,
        latest_tick=Tick(
            token=123, timestamp=datetime(2025, 10, 3, 9, 15), last_price=100, last_quantity=1,
            volume=100, open=100, high=100, low=100, close=100, oi=0
        ),
        bars_5s=[],
        bars_1s=[],
        net_liquid=1000000,
        available_margin=1000000,
        open_positions=0
    )

def test_bb_strategy_long_signal(bb_strategy, mock_context):
    """Test generating a long signal when price dips below lower band"""

    # Create data for 30 bars (enough for period 20)
    bars = []
    base_price = 100.0
    start_time = datetime(2025, 10, 3, 9, 15)

    # 29 bars at 100
    for i in range(29):
        t = start_time + timedelta(seconds=i*5)
        bar = Bar(token=123, timestamp=t, open=100, high=101, low=99, close=100, volume=100, oi=0)
        bars.append(bar)

    # 30th bar dips significantly (price 90)
    # Mean (approx 99.6), Std Dev ~ 2
    # Lower BB ~ 95
    t = start_time + timedelta(seconds=29*5)
    bar_dip = Bar(token=123, timestamp=t, open=95, high=95, low=90, close=90, volume=100, oi=0)
    bars.append(bar_dip)

    mock_context.bars_5s = bars

    signals = bb_strategy.generate_signals(mock_context)

    assert len(signals) == 1
    assert signals[0].side == SignalSide.LONG
    assert signals[0].entry_price == 90
    assert "below Lower BB" in signals[0].rationale

def test_bb_strategy_short_signal(bb_strategy, mock_context):
    """Test generating a short signal when price jumps above upper band"""

    bars = []
    start_time = datetime(2025, 10, 3, 9, 15)

    # 29 bars at 100
    for i in range(29):
        t = start_time + timedelta(seconds=i*5)
        bar = Bar(token=123, timestamp=t, open=100, high=101, low=99, close=100, volume=100, oi=0)
        bars.append(bar)

    # 30th bar jumps significantly (price 110)
    t = start_time + timedelta(seconds=29*5)
    bar_pump = Bar(token=123, timestamp=t, open=105, high=110, low=105, close=110, volume=100, oi=0)
    bars.append(bar_pump)

    mock_context.bars_5s = bars

    signals = bb_strategy.generate_signals(mock_context)

    assert len(signals) == 1
    assert signals[0].side == SignalSide.SHORT
    assert signals[0].entry_price == 110
    assert "above Upper BB" in signals[0].rationale
