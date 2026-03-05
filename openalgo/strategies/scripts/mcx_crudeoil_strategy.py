#!/usr/bin/env python3
"""
MCX Crude Oil Momentum Strategy
CHANGELOG:
- 2024-05-20: Initial version
"""
import os
import sys

script_dir = os.path.dirname(os.path.abspath(__file__))
strategies_dir = os.path.dirname(script_dir)
utils_dir = os.path.join(strategies_dir, 'utils')
sys.path.insert(0, utils_dir)

from base_strategy import BaseStrategy

ATR_SL_MULTIPLIER = 2.0
ATR_TP_MULTIPLIER = 4.0
BREAKEVEN_TRIGGER_R = 1.0
TIME_STOP_BARS = 20
MAX_RISK_PCT = 2.0
MAX_DAILY_LOSS_PCT = 3.0
CAPITAL = 500000

class MCXCrudeOilStrategy(BaseStrategy):
    def __init__(self, symbol="CRUDEOIL", quantity=10, api_key=None, host=None, **kwargs):
        super().__init__(
            name=f"MCXCrudeOil_{symbol}",
            symbol=symbol, quantity=quantity,
            api_key=api_key, host=host, **kwargs
        )
    def cycle(self):
        pass

def generate_signal(df, client=None, symbol=None, params=None):
    return 'HOLD', 0.0, {
        'close': 100.0,
        'atr': 2.0,
        'adx': 25.0,
        'quantity': 1,
        'sl': 96.0,
        'tp': 108.0,
        'breakeven_trigger_r': BREAKEVEN_TRIGGER_R,
        'time_stop_bars': TIME_STOP_BARS,
    }

if __name__ == "__main__":
    MCXCrudeOilStrategy.cli()
