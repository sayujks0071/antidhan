import pandas as pd

from packages.core.indicators import IndicatorCalculator


class VectorIndicatorCalculator(IndicatorCalculator):
    """
    Subclass to expose vector methods clearly or add missing ones.
    """
    def __init__(self, **kwargs):
        # Filter kwargs to only those accepted by IndicatorCalculator
        valid_keys = ['atr_period', 'rsi_period', 'adx_period', 'ema_fast', 'ema_slow',
                      'supertrend_period', 'supertrend_multiplier', 'bb_period', 'bb_std']
        filtered_kwargs = {k: v for k, v in kwargs.items() if k in valid_keys}
        super().__init__(**filtered_kwargs)

class IndicatorsAdapter:
    """
    Static adapter for indicators.
    """

    @staticmethod
    def rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
        calc = VectorIndicatorCalculator(rsi_period=period)
        return pd.Series(calc.rsi_series(df), index=df.index)

    @staticmethod
    def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        calc = VectorIndicatorCalculator(atr_period=period)
        return pd.Series(calc.atr_series(df), index=df.index)

    @staticmethod
    def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
        calc = VectorIndicatorCalculator(adx_period=period)
        return pd.Series(calc.adx_series(df), index=df.index)

    @staticmethod
    def ema(series: pd.Series, period: int = 14) -> pd.Series:
        # EMA doesn't need calculator state really, but for consistency
        calc = VectorIndicatorCalculator()
        return calc.ema_series(series, period)

    @staticmethod
    def supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> tuple[pd.Series, pd.Series]:
        calc = VectorIndicatorCalculator(supertrend_period=period, supertrend_multiplier=multiplier)
        val, direction = calc.supertrend_series(df)
        return pd.Series(val, index=df.index), pd.Series(direction, index=df.index)

    @staticmethod
    def bollinger_bands(series: pd.Series, period: int = 20, std: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
        calc = VectorIndicatorCalculator(bb_period=period, bb_std=std)
        return calc.bollinger_bands_series(series)

    @staticmethod
    def donchian(df: pd.DataFrame, period: int = 20) -> tuple[pd.Series, pd.Series]:
        calc = VectorIndicatorCalculator()
        return calc.donchian_series(df, period)
