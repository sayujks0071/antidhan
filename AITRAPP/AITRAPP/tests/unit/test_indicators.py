import pytest
import pandas as pd
import numpy as np
from packages.core.indicators import IndicatorCalculator

@pytest.fixture
def sample_data():
    np.random.seed(42)
    n = 100
    df = pd.DataFrame({
        'open': np.random.rand(n) * 100,
        'high': np.random.rand(n) * 100 + 100,
        'low': np.random.rand(n) * 100,
        'close': np.random.rand(n) * 100 + 50,
        'volume': np.random.randint(100, 1000, n)
    })
    # Make sure high > low
    df['high'] = np.maximum(df['high'], df['low'] + 1)
    return df

def test_atr_correctness(sample_data):
    calc = IndicatorCalculator(atr_period=14)

    # Old implementation logic using pandas
    high = sample_data["high"]
    low = sample_data["low"]
    close = sample_data["close"]
    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    # Note: The current implementation sets first element of TR to high-low
    # Standard pandas shift puts NaN.
    # The current IndicatorCalculator._calculate_tr handles this explicitly.
    # Let's rely on Calculator's TR logic and focus on rolling mean correctness.

    # Run calculator
    res = calc._atr(sample_data)

    # Verify it is not None
    assert res is not None

    # Since we are modifying the implementation, we should record the value BEFORE change
    # or implement the expected logic here.
    # Logic: Rolling mean of TR.

    tr_calc = calc.calculate_tr(sample_data)
    expected = pd.Series(tr_calc).rolling(window=14).mean().iloc[-1]

    assert np.isclose(res, expected)

def test_rsi_correctness(sample_data):
    calc = IndicatorCalculator(rsi_period=14)
    res = calc._rsi(sample_data)

    # Expected logic
    close = sample_data["close"]
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    expected = rsi.iloc[-1]

    assert np.isclose(res, expected)

def test_adx_correctness(sample_data):
    calc = IndicatorCalculator(adx_period=14)
    res = calc._adx(sample_data)

    # Expected logic
    high = sample_data["high"]
    low = sample_data["low"]

    up_move = high - high.shift()
    down_move = low.shift() - low

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)

    tr = calc.calculate_tr(sample_data)

    atr = pd.Series(tr).rolling(window=14).mean()
    plus_di = 100 * pd.Series(plus_dm).rolling(window=14).mean() / atr
    minus_di = 100 * pd.Series(minus_dm).rolling(window=14).mean() / atr

    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = dx.rolling(window=14).mean()

    expected = adx.iloc[-1]

    assert np.isclose(res, expected)

def test_bollinger_correctness(sample_data):
    calc = IndicatorCalculator(bb_period=20, bb_std=2.0)
    u, m, l = calc._bollinger_bands(sample_data["close"])

    series = sample_data["close"]
    middle = series.rolling(window=20).mean()
    std = series.rolling(window=20).std()
    upper = middle + (std * 2.0)
    lower = middle - (std * 2.0)

    assert np.isclose(u, upper.iloc[-1])
    assert np.isclose(m, middle.iloc[-1])
    assert np.isclose(l, lower.iloc[-1])
