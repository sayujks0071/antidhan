#!/usr/bin/env python3
"""
Strategy Correlation & Diversification Analysis
-----------------------------------------------
Analyzes historical performance logs to calculate correlation matrices
between strategies, helping to identify over-concentration and
improve portfolio diversification.
"""

import os
import sys
import re
import json
import logging
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, List

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("StrategyCorrelation")

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR / "strategies/logs"
ALT_LOG_DIR = BASE_DIR / "log/strategies"

def find_all_logs() -> List[Path]:
    """Find all strategy log files."""
    logs = []
    for d in [LOG_DIR, ALT_LOG_DIR]:
        if d.exists():
            logs.extend(list(d.glob("*.log")))
    return logs

def parse_pnl_series(log_file: Path) -> pd.Series:
    """
    Parse a log file to extract daily P&L series.
    Returns a Series indexed by Date.
    """
    daily_pnl = defaultdict(float)

    # Regex to find P&L updates
    # Looking for final daily summaries or individual trade exits

    # Pattern 1: [EXIT] ... pnl=123.45
    pnl_pattern = re.compile(r'pnl[:=]\s*([-\d.]+)', re.I)

    # Pattern 2: Timestamp at start of line
    time_pattern = re.compile(r'^\[?(\d{4}-\d{2}-\d{2})')

    try:
        with open(log_file, 'r', errors='ignore') as f:
            for line in f:
                # Extract Date
                time_match = time_pattern.search(line)
                if not time_match:
                    continue

                date_str = time_match.group(1)

                # Check for P&L
                # We want to capture realized P&L from exits
                if 'exit' in line.lower() or 'close' in line.lower():
                    pnl_match = pnl_pattern.search(line)
                    if pnl_match:
                        try:
                            val = float(pnl_match.group(1))
                            daily_pnl[date_str] += val
                        except ValueError:
                            pass

    except Exception as e:
        logger.error(f"Error parsing {log_file.name}: {e}")

    if not daily_pnl:
        return pd.Series(dtype=float)

    # Convert to Series
    dates = pd.to_datetime(list(daily_pnl.keys()))
    values = list(daily_pnl.values())

    s = pd.Series(values, index=dates)
    s = s.sort_index()

    # Resample to ensure continuous daily index (fill 0 for no trade days)
    if not s.empty:
        idx = pd.date_range(s.index.min(), s.index.max())
        s = s.reindex(idx, fill_value=0.0)

    return s

def clean_strategy_name(filename: str) -> str:
    """Clean log filename to get strategy name."""
    name = filename.replace('.log', '')
    # Remove timestamps if present (e.g., _20240101)
    name = re.sub(r'_\d{8}.*', '', name)
    return name

def print_heatmap(df_corr: pd.DataFrame):
    """Print a text-based heatmap of the correlation matrix."""

    symbols = [' ', '░', '▒', '▓', '█']

    print("\n🔥 CORRELATION HEATMAP (Daily P&L)")
    print("=" * 80)

    # Header
    cols = df_corr.columns
    # Create short names (first 4 chars)
    short_names = [c[:6] for c in cols]

    header = "      " + " ".join([f"{n:>6}" for n in short_names])
    print(header)
    print("      " + "-" * (len(header) - 6))

    for i, row_name in enumerate(cols):
        row_str = f"{short_names[i]:>5}|"
        for j, col_name in enumerate(cols):
            val = df_corr.iloc[i, j]

            # Map value -1 to 1 to color/symbol
            # We care mostly about high positive correlation
            if i == j:
                char = "  1.0 "
            else:
                if val > 0.7:
                    char = f"\033[91m{val:>5.2f}\033[0m" # Red for high correlation
                elif val < -0.5:
                    char = f"\033[92m{val:>5.2f}\033[0m" # Green for negative
                else:
                    char = f"{val:>5.2f} "

            row_str += f" {char}"
        print(row_str)
    print("=" * 80)
    print("Key: \033[91m> 0.70 (High Risk)\033[0m | \033[92m< -0.50 (Good Hedge)\033[0m")

def analyze_portfolio_diversification(df_pnl: pd.DataFrame, df_corr: pd.DataFrame):
    """Analyze and print diversification metrics."""
    print("\n📊 PORTFOLIO DIVERSIFICATION ANALYSIS")
    print("=" * 80)

    # 1. Identify Highly Correlated Pairs
    high_corr_pairs = []
    cols = df_corr.columns
    for i in range(len(cols)):
        for j in range(i+1, len(cols)):
            val = df_corr.iloc[i, j]
            if val > 0.7:
                high_corr_pairs.append((cols[i], cols[j], val))

    if high_corr_pairs:
        print("⚠️  HIGH CORRELATION WARNINGS (Redundant Strategies):")
        for s1, s2, val in high_corr_pairs:
            print(f"  • {s1} <-> {s2}: {val:.2f}")
            print(f"    -> Action: Reduce allocation to one or run on different assets.")
    else:
        print("✅ No highly correlated strategy pairs found.")

    print("-" * 40)

    # 2. Portfolio Variance Reduction
    # Calculate variance of equal-weight portfolio vs average individual variance
    if not df_pnl.empty:
        # Normalize returns (simple P&L)
        # Using raw P&L for variance check
        portfolio_pnl = df_pnl.sum(axis=1)
        portfolio_std = portfolio_pnl.std()

        avg_individual_std = df_pnl.std().mean()

        # Diversification Ratio (Volatility Reduction)
        # Ideally Portfolio Volatility < Sum of Individual Volatilities
        # Metric: Diversification Ratio = (Weighted Avg Vol) / Portfolio Vol
        # Simple version: Sum of Stds / Portfolio Std
        sum_std = df_pnl.std().sum()
        div_ratio = sum_std / portfolio_std if portfolio_std > 0 else 0

        print(f"Portfolio Volatility (Daily P&L Std): ₹{portfolio_std:,.2f}")
        print(f"Sum of Individual Volatilities:       ₹{sum_std:,.2f}")
        print(f"Diversification Ratio:                {div_ratio:.2f}")

        if div_ratio > 1.5:
            print("✅ Excellent Diversification (> 1.5)")
        elif div_ratio > 1.1:
            print("✅ Good Diversification (> 1.1)")
        else:
            print("⚠️  Poor Diversification (< 1.1). Strategies are moving together.")

def main():
    logs = find_all_logs()
    if not logs:
        print("No log files found in strategies/logs/")
        sys.exit(0)

    print(f"Found {len(logs)} log files. Parsing P&L data...")

    data = {}
    for log in logs:
        name = clean_strategy_name(log.name)
        series = parse_pnl_series(log)
        if not series.empty:
            # Handle duplicate names by appending index
            if name in data:
                name = f"{name}_{len(data)}"
            data[name] = series

    if not data:
        print("No P&L data extracted from logs.")
        sys.exit(0)

    # Create DataFrame
    df = pd.DataFrame(data)

    # Fill NaN with 0 (days where a strategy didn't trade)
    df = df.fillna(0)

    # Filter out empty columns (no trades ever)
    df = df.loc[:, (df != 0).any(axis=0)]

    if df.empty:
        print("No valid P&L data to analyze.")
        sys.exit(0)

    print(f"Analyzed {len(df.columns)} strategies over {len(df)} days.")

    # Calculate Correlation
    # We use valid days where at least one traded?
    # Or just use the zero-filled series?
    # Using zero-filled captures the "activity correlation" too.

    corr_matrix = df.corr()

    print_heatmap(corr_matrix)
    analyze_portfolio_diversification(df, corr_matrix)

if __name__ == "__main__":
    main()
