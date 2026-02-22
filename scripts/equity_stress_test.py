import pandas as pd
import re

def parse_audit_table(filepath):
    """Parses the Markdown table from audit_results.md."""
    data = []
    with open(filepath, 'r') as f:
        lines = f.readlines()

    in_table = False
    for line in lines:
        if "| strategy" in line:
            in_table = True
            continue
        if in_table and "|---" in line:
            continue
        if in_table:
            if not line.strip().startswith("|"):
                in_table = False
                continue

            # Parse row
            # | 44 | ORB | FINNIFTY | LONG | 20361.6 |
            parts = [p.strip() for p in line.split('|') if p.strip()]
            if len(parts) >= 5:
                # parts[0] is index, parts[1] is strategy, etc.
                try:
                    row = {
                        'strategy': parts[1],
                        'symbol': parts[2],
                        'direction': parts[3],
                        'pnl': float(parts[4])
                    }
                    data.append(row)
                except ValueError:
                    continue
    return pd.DataFrame(data)

def analyze_stress_test():
    filepath = "audit_results.md"
    print(f"Parsing {filepath}...")

    df = parse_audit_table(filepath)

    if df.empty:
        print("No trades found in audit results.")
        return

    print(f"\nTotal Trades Parsed: {len(df)}")

    total_pnl = df['pnl'].sum()
    print(f"Total PnL (Worst Day): {total_pnl:.2f}")

    # PnL by Strategy
    print("\n=== PnL by Strategy ===")
    strategy_pnl = df.groupby('strategy')['pnl'].sum().sort_values()
    print(strategy_pnl)

    # Root Cause Analysis
    print("\n=== Root Cause Analysis ===")

    # Check correlation of losses
    losers = df[df['pnl'] < 0]
    print(f"Number of Losing Trades: {len(losers)}")

    # Group losers by strategy
    losers_by_strategy = losers.groupby('strategy')['pnl'].count()
    print("Losing Trades by Strategy:")
    print(losers_by_strategy)

    # Check for sector/symbol concentration
    losers_by_symbol = losers.groupby('symbol')['pnl'].sum().sort_values()
    print("\nLargest Losses by Symbol:")
    print(losers_by_symbol.head(3))

    # Findings
    print("\n=== Findings ===")
    if 'ORB' in strategy_pnl and 'TrendPullback' in strategy_pnl:
         # Check if they moved together
         orb_pnl = strategy_pnl.get('ORB', 0)
         tp_pnl = strategy_pnl.get('TrendPullback', 0)
         print(f"ORB PnL: {orb_pnl:.2f}")
         print(f"TrendPullback PnL: {tp_pnl:.2f}")

         if orb_pnl < 0 and tp_pnl < 0:
             print("Both ORB and TrendPullback failed. Confirms High Correlation risk.")
         elif orb_pnl > 0 and tp_pnl < 0:
             print("ORB Profited while TrendPullback failed. Divergence despite 1.0 correlation?")
         elif orb_pnl > 0 and tp_pnl > 0:
             print("Both Profited. Why was this the 'Worst Day'?")

    # SuperTrendVWAP check
    st_pnl = strategy_pnl.get('SuperTrendVWAP', 0)
    print(f"SuperTrendVWAP PnL: {st_pnl:.2f}")

    if total_pnl > 0:
        print("\n[Wait] Total PnL is POSITIVE. The 'Worst Day' label in audit_results.md might refer to a different dataset or calculation, or the table only shows a subset.")
    else:
        print("\n[Confirmed] Net Loss matches expectation.")

if __name__ == "__main__":
    analyze_stress_test()
