from datetime import datetime, timedelta

import pytest

from packages.core.models import Bar, Instrument, InstrumentType, SignalSide, Tick
from packages.core.strategies.base import StrategyContext
from packages.core.strategies.orb import ORBStrategy


@pytest.fixture
def orb_strategy():
    return ORBStrategy("ORB", {"window_min": 15})

@pytest.fixture
def mock_context():
    instrument = Instrument(
        token=123,
        symbol="NIFTY",
        tradingsymbol="NIFTY25SEP25000CE",
        exchange="NFO",
        instrument_type=InstrumentType.CE,
        strike=25000,
        lot_size=50,
        tick_size=0.05
    )
    return StrategyContext(
        timestamp=datetime(2025, 10, 3, 9, 15), # Start at 9:15
        instrument=instrument,
        latest_tick=Tick(
            token=123, timestamp=datetime(2025, 10, 3, 9, 15), last_price=100, last_quantity=1,
            volume=100, open=100, high=100, low=100, close=100, oi=0
        ),
        bars_5s=[],
        bars_1s=[],
        net_liquid=1000000,
        available_margin=800000,
        open_positions=0
    )

def test_orb_strategy_logic_flow(orb_strategy, mock_context):
    """
    Test that ORB strategy correctly:
    1. Observes data during opening range (9:15 - 9:30)
    2. Sets the opening range at 9:30
    3. Generates signal on breakout after 9:30
    """

    # 1. Simulate Market Open (9:15 - 9:30)
    # We feed it bars. High=110, Low=90.
    start_time = datetime(2025, 10, 3, 9, 15)

    # Generate some bars for the first 15 mins
    bars = []
    for i in range(15 * 12): # 15 mins * 12 (5s bars)
        t = start_time + timedelta(seconds=i*5)
        bar = Bar(
            token=123,
            timestamp=t,
            open=100, high=110 if i == 5 else 100, low=90 if i == 10 else 100, close=100,
            volume=100, oi=0
        )
        bars.append(bar)

        # Update context
        mock_context.timestamp = t
        mock_context.bars_5s = bars

        # Run strategy
        orb_strategy.generate_signals(mock_context)

    # At 9:30:00 (exact end of window), or shortly after
    mock_context.timestamp = datetime(2025, 10, 3, 9, 30, 5)
    orb_strategy.generate_signals(mock_context)

    # Check if opening range was captured
    # The bug is that validate() prevents execution before 9:30, so range is never captured.

    if 123 not in orb_strategy.opening_ranges:
        print("\nBUG REPRODUCED: Opening range not captured because generate_signals was blocked during window.")
    else:
        print(f"\nRange captured: {orb_strategy.opening_ranges[123]}")

    assert 123 in orb_strategy.opening_ranges, "Opening range should be set after window closes"

    high, low, end_time = orb_strategy.opening_ranges[123]
    assert high == 110
    assert low == 90

    # 2. Simulate Breakout (9:31)
    mock_context.timestamp = datetime(2025, 10, 3, 9, 31)
    mock_context.latest_tick.last_price = 112 # Breakout above 110

    # We need confirmation ticks (default 3)
    # Tick 1
    signals = orb_strategy.generate_signals(mock_context)
    assert len(signals) == 0, "Should wait for confirmation (Tick 1)"

    # Tick 2
    signals = orb_strategy.generate_signals(mock_context)
    assert len(signals) == 0, "Should wait for confirmation (Tick 2)"

    # Tick 3
    signals = orb_strategy.generate_signals(mock_context)
    assert len(signals) == 0, "Should wait for confirmation (Tick 3 - logic check)"

    # Wait, the logic is:
    # if not confirmed: increment, return []
    # return confirmed? NO.

    # Let's trace carefully:
    # Call 1: confirmed? No. Increment (count=1). Return [].
    # Call 2: confirmed? No. Increment (count=2). Return [].
    # Call 3: confirmed? No. Increment (count=3). Return [].
    # Call 4: confirmed? YES (count=3 >= 3). Proceed to generate signal.

    # Tick 4
    signals = orb_strategy.generate_signals(mock_context)
    assert len(signals) == 1, "Should generate signal after confirmation ticks"

    signal = signals[0]
    assert signal.side == SignalSide.LONG
    assert signal.entry_price == 112
    assert signal.stop_loss == 90
