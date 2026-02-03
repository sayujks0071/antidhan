import hashlib
import json
import random
from typing import Any, Dict

import pandas as pd

from packages.strategy_foundry.adapters.core_indicators import IndicatorsAdapter
from packages.strategy_foundry.factory.grammar import Filter, Rule, StrategyConfig
from packages.strategy_foundry.factory.parameter_space import ParameterSpace


class StrategyGenerator:
    def generate_candidate(self) -> StrategyConfig:
        """Generates a random strategy configuration using grammar blocks."""

        # 1. Choose Entry Logic (1-2 blocks)
        entry_logic_type = random.choice(['breakout', 'trend', 'reversion'])
        entry_rules = []

        if entry_logic_type == 'breakout':
            # Donchian Breakout or Bollinger Breakout
            if random.random() < 0.5:
                # Donchian High Breakout
                period = random.choice([20, 55])
                entry_rules.append(Rule('breakout', 'donchian', {'period': period}, '>', 'upper'))
            else:
                # BB Breakout
                params = ParameterSpace.get_random_params('bollinger')
                entry_rules.append(Rule('breakout', 'bollinger', params, '>', 'upper'))

        elif entry_logic_type == 'trend':
            # EMA Cross or Supertrend
            if random.random() < 0.5:
                # Price > EMA
                params = ParameterSpace.get_random_params('ema')
                entry_rules.append(Rule('trend', 'ema', params, '>', 'close')) # close > ema
                # Wait, Rule structure: indicator vs value.
                # If indicator=ema, val=close -> ema > close (Bearish).
                # We want close > ema. So indicator='close', val='ema'.
                # But my Rule def has indicator, operator, value.
                # Let's say: indicator 'ema' > 'close' means EMA > Close.
                # For Trend Long: Close > EMA. -> EMA < Close.
                entry_rules.append(Rule('trend', 'ema', params, '<', 'close'))
            else:
                # Supertrend Bullish
                params = ParameterSpace.get_random_params('supertrend')
                entry_rules.append(Rule('trend', 'supertrend', params, '==', 1)) # direction == 1

        elif entry_logic_type == 'reversion':
            # RSI Oversold or BB Lower bounce
            if random.random() < 0.5:
                params = ParameterSpace.get_random_params('rsi')
                thresh = random.choice([30, 40])
                entry_rules.append(Rule('reversion', 'rsi', params, '<', thresh))
            else:
                params = ParameterSpace.get_random_params('bollinger')
                entry_rules.append(Rule('reversion', 'bollinger', params, '<', 'lower')) # Close < Lower

        # 2. Add Filters (0-2)
        filters = []
        if random.random() < 0.5:
            # ADX Filter (Trend Strength)
            params = ParameterSpace.get_random_params('adx')
            thresh = random.choice([20, 25])
            filters.append(Filter('volatility', 'adx', params, '>', thresh))

        # 3. Risk Params
        sl = random.choice([1.0, 1.5, 2.0, 3.0])
        tp = random.choice([2.0, 3.0, 4.0, 5.0])
        max_bars = random.choice([12, 24, 36, 75]) # Intraday horizons (e.g. 5m bars: 12=1h)

        # Generate ID
        config_dict = {
            "entry": [vars(r) for r in entry_rules],
            "filters": [vars(f) for f in filters],
            "sl": sl,
            "tp": tp,
            "max_bars": max_bars
        }
        sid = hashlib.md5(json.dumps(config_dict, sort_keys=True).encode()).hexdigest()[:8]

        return StrategyConfig(
            strategy_id=sid,
            entry_rules=entry_rules,
            filters=filters,
            stop_loss_atr=sl,
            take_profit_atr=tp,
            trailing_stop_atr=None,
            max_bars_hold=max_bars
        )

    def generate_signal(self, df: pd.DataFrame, config: StrategyConfig) -> pd.Series:
        """
        Generates Entry Signal (1 = Buy, 0 = None).
        Does NOT handle exits (Backtest engine handles exits).
        """
        # Base Signal
        signal = pd.Series(True, index=df.index)

        # Apply Entry Rules
        for rule in config.entry_rules:
            cond = self._evaluate_condition(df, rule.indicator, rule.operator, rule.threshold, rule.params)
            signal = signal & cond

        # Apply Filters
        for filt in config.filters:
            cond = self._evaluate_condition(df, filt.indicator, filt.operator, filt.threshold, filt.params)
            signal = signal & cond

        # Convert boolean to integer signal (1)
        # Usually strategies trigger on crossover (False -> True)
        # But some might be "State" based (Close > EMA).
        # If we return "State", the engine will enter on first 0->1 transition.
        # If we return "State", we might re-enter immediately after exit if condition persists?
        # Standard: Return State. Engine handles re-entry logic (usually "wait for new signal" or "re-enter allowed").
        # Requirements says "No pyramiding by default".

        return signal.astype(int)

    def _evaluate_condition(self, df: pd.DataFrame, indicator: str, operator: str, threshold: Any, params: Dict) -> pd.Series:
        # Special composite handling first
        if indicator == 'bollinger':
            u, m, l = IndicatorsAdapter.bollinger_bands(df['close'], **params)
            if threshold == 'upper':
                return df['close'] > u if operator == '>' else df['close'] < u
            elif threshold == 'lower':
                return df['close'] < l if operator == '<' else df['close'] > l

        if indicator == 'donchian':
            u, l = IndicatorsAdapter.donchian(df, **params)
            if threshold == 'upper':
                 return df['close'] > u if operator == '>' else df['close'] < u
            elif threshold == 'lower':
                 return df['close'] < l if operator == '<' else df['close'] > l

        # Standard LHS
        if indicator == 'close':
            lhs = df['close']
        elif indicator == 'rsi':
            lhs = IndicatorsAdapter.rsi(df, **params)
        elif indicator == 'adx':
            lhs = IndicatorsAdapter.adx(df, **params)
        elif indicator == 'ema':
            lhs = IndicatorsAdapter.ema(df['close'], **params)
        elif indicator == 'supertrend':
            st, direction = IndicatorsAdapter.supertrend(df, **params)
            if threshold == 1 or threshold == -1:
                lhs = direction
            else:
                lhs = st
        else:
            lhs = pd.Series(0, index=df.index)

        # Standard RHS
        if threshold == 'close':
            rhs = df['close']
        else:
            rhs = threshold

        # Comparison
        if operator == '>':
            return lhs > rhs
        elif operator == '<':
            return lhs < rhs
        elif operator == '==':
            return lhs == rhs

        return pd.Series(False, index=df.index)
