import numpy as np
import pandas as pd


class MetricCalculator:
    @staticmethod
    def compute(trades: pd.DataFrame, time_span_years: float) -> dict:
        if trades.empty:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "avg_return": 0.0,
                "sharpe": -99.9,
                "sortino": -99.9,
                "max_dd": 1.0, # 100% DD
                "cagr": 0.0,
                "calmar": 0.0,
                "stability": 0.0,
                "avg_bars_held": 0.0
            }

        returns = trades['net_return']

        # Basic Counts
        total_trades = len(trades)
        wins = returns[returns > 0]
        losses = returns[returns <= 0]

        win_rate = len(wins) / total_trades

        gross_profit = wins.sum()
        gross_loss = abs(losses.sum())
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 99.9

        avg_return = returns.mean()

        # Risk Metrics
        # Assume these are per-trade returns.
        # Sharpe per trade? Or annualized?
        # Sharpe = (Mean per trade / Std per trade) * sqrt(Trades per year)
        # Trades per year = Total Trades / Years

        trades_per_year = total_trades / time_span_years if time_span_years > 0 else total_trades

        std_return = returns.std()
        if std_return == 0:
             sharpe = 0.0
        else:
             sharpe = (avg_return / std_return) * np.sqrt(trades_per_year)

        # Sortino (std of downside)
        downside = returns[returns < 0]
        std_downside = downside.std()
        if std_downside == 0 or len(downside) < 2:
            sortino = sharpe # fallback
        else:
            sortino = (avg_return / std_downside) * np.sqrt(trades_per_year)

        # Drawdown (Equity Curve)
        # Cumulative Compounded
        equity = (1 + returns).cumprod()
        peak = equity.cummax()
        drawdown = (equity - peak) / peak
        max_dd = abs(drawdown.min())

        # CAGR
        # Final Equity
        final_eq = equity.iloc[-1]
        cagr = (final_eq ** (1 / time_span_years)) - 1 if time_span_years > 0 and final_eq > 0 else 0.0

        # Calmar
        calmar = cagr / max_dd if max_dd > 0 else 0.0

        # Stability (Rolling Sharpe Volatility?)
        # Or simple R-squared of equity curve?
        # Let's use fold variance (handled in Walkforward).
        # Here we can compute R-squared of log equity.

        # Late Day Dependence
        # Not implemented here yet, needs timestamps in trades DF.

        return {
            "total_trades": total_trades,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "avg_return": avg_return,
            "sharpe": sharpe,
            "sortino": sortino,
            "max_dd": max_dd,
            "cagr": cagr,
            "calmar": calmar,
            "avg_bars_held": trades['bars_held'].mean()
        }
