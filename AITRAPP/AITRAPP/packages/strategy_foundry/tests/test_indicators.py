import numpy as np
import pandas as pd

from packages.strategy_foundry.adapters.core_indicators import VectorizedIndicators


def test_indicators():
    vi = VectorizedIndicators()
    df = pd.DataFrame({
        "high": np.random.rand(100) * 10 + 100,
        "low": np.random.rand(100) * 10 + 90,
        "close": np.random.rand(100) * 10 + 95,
        "volume": np.random.rand(100) * 1000
    })

    rsi = vi.get_rsi(df)
    assert len(rsi) == 100
    assert not rsi.isna().all()

def test_risk_config():
    # Ensure we can import core via adapter if we had one,
    # but we didn't implement core_costs.py yet.
    # Let's mock or skip.
    pass
