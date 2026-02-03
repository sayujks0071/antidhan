import pandas as pd
import pytest

from packages.strategy_foundry.backtest.engine import FoundryEngine


def test_short_trade_profit():
    """Verify that a short trade in a falling market yields positive PnL."""
    dates = pd.date_range(start="2024-01-01", periods=4, freq="D")
    df = pd.DataFrame({
        "open": [100.0, 100.0, 90.0, 90.0]
    }, index=dates)

    # Day 1: Signal -1. Day 2: Enter Short (Open 100).
    # Day 2: Signal 0. Day 3: Exit Short (Open 90).
    positions = pd.Series([-1, 0, 0, 0], index=dates)

    engine = FoundryEngine(slip_bps=0, fee_bps=0)
    result = engine.run(df, positions)
    trades = result["trades"]

    assert len(trades) == 1
    trade = trades[0]

    assert trade.side == -1
    assert trade.entry_price == 100.0
    assert trade.exit_price == 90.0
    assert trade.pnl > 0
    assert pytest.approx(trade.pnl) == 10.0
    assert pytest.approx(trade.pnl_pct) == 0.10

def test_long_trade_profit():
    """Verify that a long trade in a rising market yields positive PnL."""
    dates = pd.date_range(start="2024-01-01", periods=4, freq="D")
    df = pd.DataFrame({
        "open": [100.0, 100.0, 110.0, 110.0]
    }, index=dates)

    # Day 1: Signal 1. Day 2: Enter Long (Open 100).
    # Day 2: Signal 0. Day 3: Exit Long (Open 110).
    positions = pd.Series([1, 0, 0, 0], index=dates)

    engine = FoundryEngine(slip_bps=0, fee_bps=0)
    result = engine.run(df, positions)
    trades = result["trades"]

    assert len(trades) == 1
    trade = trades[0]

    assert trade.side == 1
    assert trade.entry_price == 100.0
    assert trade.exit_price == 110.0
    assert trade.pnl > 0
    assert pytest.approx(trade.pnl) == 10.0
    assert pytest.approx(trade.pnl_pct) == 0.10

def test_slippage_logic():
    """Verify that slippage is applied correctly based on direction."""
    # Market: Flat 100.
    dates = pd.date_range(start="2024-01-01", periods=10, freq="D")
    df = pd.DataFrame({
        "open": [100.0] * 10
    }, index=dates)

    slip_bps = 100 # 1%
    engine = FoundryEngine(slip_bps=slip_bps, fee_bps=0)

    # Case 1: Long
    # Day 1: Signal 1. Day 2: Enter Long. Price 100. Entry = 100 * 1.01 = 101.
    # Day 2: Signal 0. Day 3: Exit Long. Price 100. Exit = 100 * 0.99 = 99.
    pos_long = pd.Series([0, 1, 0, 0, 0, 0, 0, 0, 0, 0], index=dates)
    result_long = engine.run(df, pos_long)
    t_long = result_long["trades"][0]

    assert t_long.side == 1
    assert pytest.approx(t_long.entry_price) == 101.0
    assert pytest.approx(t_long.exit_price) == 99.0

    # Case 2: Short
    # Day 1: Signal -1. Day 2: Enter Short. Price 100. Entry = 100 * 0.99 = 99.
    # Day 2: Signal 0. Day 3: Exit Short. Price 100. Exit = 100 * 1.01 = 101.
    pos_short = pd.Series([0, -1, 0, 0, 0, 0, 0, 0, 0, 0], index=dates)
    result_short = engine.run(df, pos_short)
    t_short = result_short["trades"][0]

    assert t_short.side == -1
    assert pytest.approx(t_short.entry_price) == 99.0
    assert pytest.approx(t_short.exit_price) == 101.0
