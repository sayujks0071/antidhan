#!/usr/bin/env python3
"""
VectorBT Premium Strategies Runner
----------------------------------
Backtests multiple strategies (EMA, RSI, MACD, Bollinger) across NSE/MCX symbols
using VectorBT. Selects top 10 premium strategies by Sharpe, return, and drawdown.
Target: support path to ₹1,00,000/day potential (see PREMIUM_STRATEGIES_REPORT.md).
Uses OpenAlgo history API; optional yfinance fallback for NSE equities.
"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
import requests
import vectorbt as vbt
from dotenv import load_dotenv


# -----------------------------------------------------------------------------
# Premium criteria (strategies must meet these to be "premium")
# -----------------------------------------------------------------------------
MIN_SHARPE = 0.5
MAX_DRAWDOWN_PCT = 20.0   # e.g. -15% => 15% max drawdown allowed
MIN_TRADES = 5
MIN_NET_PROFIT = 0.0
TARGET_DAILY_PROFIT_INR = 100_000   # ₹1 Lakh/day goal (for reporting)


@dataclass
class StrategyResult:
    strategy_name: str
    symbol: str
    exchange: str
    interval: str
    params: dict[str, Any]
    total_return_pct: float
    max_drawdown_pct: float
    sharpe: float
    trades: int
    net_profit: float
    trading_days: int
    daily_profit_avg: float
    rejected: bool
    reject_reason: str = ""
    score: float = 0.0


def _history(
    host: str,
    api_key: str,
    symbol: str,
    exchange: str,
    interval: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    url = f"{host.rstrip('/')}/api/v1/history"
    payload = {
        "apikey": api_key,
        "symbol": symbol,
        "exchange": exchange,
        "interval": interval,
        "start_date": start_date,
        "end_date": end_date,
    }
    resp = requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") != "success":
        raise RuntimeError(f"history failed for {symbol}: {data}")
    rows = data.get("data", [])
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if "timestamp" in df.columns:
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="s", errors="coerce")
    elif "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    else:
        df["datetime"] = pd.to_datetime(df.index, errors="coerce")
    df = df.dropna(subset=["datetime"]).sort_values("datetime").set_index("datetime")
    for c in ("open", "high", "low", "close", "volume"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=["close"])


def _history_yf(symbol: str, exchange: str, start_date: str, end_date: str, interval: str) -> pd.DataFrame:
    """Fallback: fetch daily data via yfinance for NSE equities. MCX not supported."""
    try:
        import yfinance as yf
    except ImportError:
        return pd.DataFrame()
    if exchange.upper() not in ("NSE", "NSE_INDEX"):
        return pd.DataFrame()
    ticker = f"{symbol}.NS" if exchange == "NSE" else f"^{symbol.replace(' ', '')}.NS"
    if "NIFTY" in symbol.upper():
        ticker = "^NSEI"
    elif "BANKNIFTY" in symbol.upper() or "BANK NIFTY" in symbol.upper():
        ticker = "^NSEBANK"
    period = "1y"
    try:
        data = yf.download(ticker, start=start_date, end=end_date, interval="1d", progress=False, auto_adjust=True)
    except Exception:
        return pd.DataFrame()
    if data.empty or len(data) < 30:
        return pd.DataFrame()
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = [c[0].lower() if isinstance(c, tuple) else str(c).lower() for c in data.columns]
    else:
        data.columns = [str(c).lower() for c in data.columns]
    data = data.rename(columns={"adj close": "close"} if "adj close" in data.columns else {})
    if "close" not in data.columns and len(data.columns):
        data["close"] = data.iloc[:, -1]
    data.index = pd.to_datetime(data.index)
    data = data.dropna(subset=["close"])
    return data[["open", "high", "low", "close", "volume"]].copy() if "volume" in data.columns else data


def _resolve_symbol(host: str, api_key: str, query: str, exchange: str) -> str:
    url = f"{host.rstrip('/')}/api/v1/search"
    payload = {"apikey": api_key, "query": query, "exchange": exchange}
    try:
        resp = requests.post(url, json=payload, timeout=20)
        if resp.status_code != 200:
            return query
        data = resp.json()
        rows = data.get("data", [])
        if not rows:
            return query
        for row in rows:
            if str(row.get("symbol", "")).upper() == query.upper():
                return str(row.get("symbol"))
        return str(rows[0].get("symbol") or query)
    except Exception:
        return query


def _run_portfolio(
    close: pd.Series,
    entries: pd.Series,
    exits: pd.Series,
    init_cash: float,
    fees: float,
    freq: str,
) -> dict[str, Any]:
    pf = vbt.Portfolio.from_signals(
        close,
        entries,
        exits,
        direction="longonly",
        init_cash=init_cash,
        fees=fees,
        size=1.0,
        size_type="percent",
        freq=freq,
    )
    total_return = float(pf.total_return())
    max_dd = float(pf.max_drawdown())
    sharpe = float(pf.sharpe_ratio()) if np.isfinite(float(pf.sharpe_ratio())) else 0.0
    trades = int(pf.trades.count())
    net_profit = float(init_cash * total_return)
    return {
        "total_return_pct": total_return * 100.0,
        "max_drawdown_pct": max_dd * 100.0,
        "sharpe": sharpe,
        "trades": trades,
        "net_profit": net_profit,
    }


# --------------- Strategy definitions (return entries, exits) ---------------
def strategy_ema(close: pd.Series, fast: int = 10, slow: int = 20) -> tuple[pd.Series, pd.Series]:
    fast_ma = vbt.MA.run(close, fast, ewm=True)
    slow_ma = vbt.MA.run(close, slow, ewm=True)
    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)
    return entries, exits


def strategy_rsi(close: pd.Series, window: int = 14, entry_rsi: float = 30, exit_rsi: float = 70) -> tuple[pd.Series, pd.Series]:
    rsi = vbt.RSI.run(close, window=window)
    # Entry when RSI crosses below oversold; exit when crosses above overbought
    if hasattr(rsi, "rsi_crossed_below"):
        entries = rsi.rsi_crossed_below(entry_rsi)
        exits = rsi.rsi_crossed_above(exit_rsi)
    else:
        entries = rsi.rsi_below(entry_rsi) & ~rsi.rsi_below(entry_rsi).shift(1).fillna(False)
        exits = rsi.rsi_above(exit_rsi) & ~rsi.rsi_above(exit_rsi).shift(1).fillna(False)
    return entries, exits


def strategy_macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series]:
    macd = vbt.MACD.run(close, fast_window=fast, slow_window=slow, signal_window=signal)
    entries = macd.macd_crossed_above(macd.signal)
    exits = macd.macd_crossed_below(macd.signal)
    return entries, exits


def strategy_bollinger(close: pd.Series, window: int = 20, alpha: float = 2.0) -> tuple[pd.Series, pd.Series]:
    bb = vbt.BBANDS.run(close, window=window, alpha=alpha)
    entries = close <= bb.lower  # price at or below lower band -> buy
    exits = close >= bb.upper   # price at or above upper band -> sell
    return entries, exits


def strategy_sma_crossover(close: pd.Series, fast: int = 10, slow: int = 30) -> tuple[pd.Series, pd.Series]:
    fast_ma = vbt.MA.run(close, fast, ewm=False)
    slow_ma = vbt.MA.run(close, slow, ewm=False)
    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)
    return entries, exits


# Registry: name -> (fn, default_params_list)
STRATEGY_REGISTRY: list[tuple[str, Callable[..., tuple[pd.Series, pd.Series]], list[dict]]] = [
    ("EMA_Crossover", strategy_ema, [{"fast": 8, "slow": 21}, {"fast": 10, "slow": 20}, {"fast": 12, "slow": 26}]),
    ("SMA_Crossover", strategy_sma_crossover, [{"fast": 10, "slow": 30}, {"fast": 20, "slow": 50}]),
    ("RSI_Reversal", strategy_rsi, [{"window": 14, "entry_rsi": 30, "exit_rsi": 70}, {"window": 14, "entry_rsi": 25, "exit_rsi": 75}]),
    ("MACD_Crossover", strategy_macd, [{"fast": 12, "slow": 26, "signal": 9}]),
    ("Bollinger_MeanRev", strategy_bollinger, [{"window": 20, "alpha": 2.0}, {"window": 15, "alpha": 2.0}]),
]


def run_one_strategy(
    df: pd.DataFrame,
    strategy_name: str,
    strategy_fn: Callable,
    params: dict,
    init_cash: float,
    fees: float,
    freq: str,
    symbol: str,
    exchange: str,
    interval: str,
    trading_days: int,
) -> StrategyResult | None:
    if df.empty or len(df) < 50:
        return None
    close = df["close"]
    try:
        entries, exits = strategy_fn(close, **params)
    except Exception:
        return None
    metrics = _run_portfolio(close, entries, exits, init_cash, fees, freq)
    max_dd_pct = abs(metrics["max_drawdown_pct"])
    rejected = (
        metrics["sharpe"] < MIN_SHARPE
        or max_dd_pct > MAX_DRAWDOWN_PCT
        or metrics["trades"] < MIN_TRADES
        or metrics["net_profit"] < MIN_NET_PROFIT
    )
    days = max(1, trading_days)
    daily_avg = metrics["net_profit"] / days
    return StrategyResult(
        strategy_name=strategy_name,
        symbol=symbol,
        exchange=exchange,
        interval=interval,
        params=params,
        total_return_pct=metrics["total_return_pct"],
        max_drawdown_pct=metrics["max_drawdown_pct"],
        sharpe=metrics["sharpe"],
        trades=metrics["trades"],
        net_profit=metrics["net_profit"],
        trading_days=days,
        daily_profit_avg=daily_avg,
        rejected=rejected,
        reject_reason="premium_criteria" if rejected else "",
    )


def score_result(r: StrategyResult) -> float:
    """Higher is better. Sharpe and return positive; drawdown negative."""
    sharpe_part = min(3.0, max(0, r.sharpe)) / 3.0
    return_part = min(50.0, max(0, r.total_return_pct)) / 50.0
    dd_part = 1.0 - min(1.0, abs(r.max_drawdown_pct) / 30.0)
    trades_part = min(1.0, r.trades / 30.0)
    return 0.35 * sharpe_part + 0.35 * return_part + 0.2 * dd_part + 0.1 * trades_part


def main() -> None:
    parser = argparse.ArgumentParser(description="VectorBT Premium Strategies - top 10 for ₹1L/day potential")
    parser.add_argument("--host", default="http://127.0.0.1:5002")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--interval", default="15m")
    parser.add_argument("--init-cash", type=float, default=100_000.0)
    parser.add_argument("--fees", type=float, default=0.0011)
    parser.add_argument("--use-yf", action="store_true", help="Use yfinance fallback for NSE (daily only)")
    parser.add_argument("--out", default="")
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()

    load_dotenv(Path(__file__).resolve().parents[1] / "openalgo" / ".env", override=False)
    api_key = args.api_key or os.getenv("OPENALGO_API_KEY") or os.getenv("OPENALGO_APIKEY")

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
    trading_days = max(1, args.days * 252 // 365)  # approx trading days

    freq_map = {"1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min", "60m": "1h", "1h": "1h", "D": "1D", "1d": "1D"}
    freq = freq_map.get(args.interval, "15min")

    universe = [
        ("CRUDEOIL", "MCX"),
        ("GOLD", "MCX"),
        ("SILVER", "MCX"),
        ("NATURALGAS", "MCX"),
        ("NIFTY", "NSE_INDEX"),
        ("BANKNIFTY", "NSE_INDEX"),
        ("RELIANCE", "NSE"),
        ("SBIN", "NSE"),
        ("HDFCBANK", "NSE"),
        ("ICICIBANK", "NSE"),
        ("TCS", "NSE"),
        ("INFY", "NSE"),
    ]

    all_results: list[StrategyResult] = []

    for symbol, exchange in universe:
        df = None
        if api_key and not args.use_yf:
            try:
                resolved = _resolve_symbol(args.host, api_key, symbol, exchange)
                df = _history(args.host, api_key, resolved, exchange, args.interval, start_date, end_date)
            except Exception:
                try:
                    df = _history(args.host, api_key, symbol, exchange, args.interval, start_date, end_date)
                except Exception:
                    pass
        if df is None or df.empty:
            if args.use_yf:
                df = _history_yf(symbol, exchange, start_date, end_date, args.interval)
            if df is None or df.empty:
                continue
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        days_actual = (df.index.max() - df.index.min()).days if len(df) else trading_days
        days_actual = max(1, days_actual)

        for strategy_name, strategy_fn, param_list in STRATEGY_REGISTRY:
            for params in param_list:
                res = run_one_strategy(
                    df,
                    strategy_name,
                    strategy_fn,
                    params,
                    args.init_cash,
                    args.fees,
                    freq,
                    symbol,
                    exchange,
                    args.interval,
                    days_actual,
                )
                if res is None:
                    continue
                res.score = score_result(res)
                all_results.append(res)

    # Sort: non-rejected first, then by score desc, then by net_profit
    all_results.sort(key=lambda x: (x.rejected, -x.score, -x.net_profit))

    # Top N unique (strategy_name + symbol)
    seen = set()
    top_results: list[StrategyResult] = []
    for r in all_results:
        key = (r.strategy_name, r.symbol)
        if key in seen or r.rejected:
            continue
        seen.add(key)
        top_results.append(r)
        if len(top_results) >= args.top:
            break

    # If we have fewer than top N premium, add best rejected to fill
    if len(top_results) < args.top:
        for r in all_results:
            if r.rejected and (r.strategy_name, r.symbol) not in seen:
                top_results.append(r)
                seen.add((r.strategy_name, r.symbol))
                if len(top_results) >= args.top:
                    break

    total_daily_avg = sum(r.daily_profit_avg for r in top_results)
    report = {
        "generated_at": datetime.now().isoformat(),
        "host": args.host,
        "interval": args.interval,
        "start_date": start_date,
        "end_date": end_date,
        "target_daily_profit_inr": TARGET_DAILY_PROFIT_INR,
        "premium_criteria": {
            "min_sharpe": MIN_SHARPE,
            "max_drawdown_pct": MAX_DRAWDOWN_PCT,
            "min_trades": MIN_TRADES,
        },
        "top_premium_strategies": [asdict(r) for r in top_results],
        "total_daily_profit_avg_projectation": total_daily_avg,
        "note": "Backtest does not guarantee future results. 1L/day is a target; scale capital and risk accordingly.",
    }

    out_path = args.out or str(Path(__file__).resolve().parents[1] / "log" / "vectorbt_premium_strategies_report.json")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps({
        "status": "ok",
        "report_path": out_path,
        "top_count": len(top_results),
        "total_daily_avg_projection_inr": round(total_daily_avg, 2),
        "target_1l_per_day": TARGET_DAILY_PROFIT_INR,
    }, indent=2))


if __name__ == "__main__":
    main()
