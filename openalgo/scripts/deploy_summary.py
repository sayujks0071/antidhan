#!/usr/bin/env python3
"""Summary of strategies ready to deploy based on rankings."""
import csv
from pathlib import Path

STRATEGY_FILE_MAP = {
    "NIFTY Greeks Enhanced": "nifty_greeks_enhanced_20260122.py",
    "NIFTY Multi-Strike Momentum": "nifty_multistrike_momentum_20260122.py",
    "NIFTY AITRAPP Options Ranker": "nifty_aitrapp_options_ranker_20260122.py",
    "NIFTY Spread Strategy": "nifty_spread_strategy_20260122.py",
    "NIFTY Iron Condor": "nifty_iron_condor_20260122.py",
    "NIFTY Gamma Scalping": "nifty_gamma_scalping_20260122.py",
    "SENSEX Greeks Enhanced": "sensex_greeks_enhanced_20260122.py",
    "SENSEX Multi-Strike Momentum": "sensex_multistrike_momentum_20260122.py",
}

rankings_csv = Path("/Users/mac/dyad-apps/openalgo/strategies/openalgo/strategies/backtest_results/strategy_rankings.csv")
scripts_dir = Path("/Users/mac/dyad-apps/openalgo/strategies/scripts")

print("=" * 80)
print("TOP RANKED STRATEGIES READY FOR DEPLOYMENT")
print("=" * 80)

if rankings_csv.exists():
    with rankings_csv.open() as f:
        reader = csv.DictReader(f)
        rankings = sorted([row for row in reader], key=lambda x: int(x.get('rank', 999)))
    
    print(f"\nFound {len(rankings)} ranked strategies\n")
    
    for i, entry in enumerate(rankings[:3], 1):
        strategy_name = entry.get('strategy', '')
        filename = STRATEGY_FILE_MAP.get(strategy_name, '')
        file_path = scripts_dir / filename if filename else None
        
        print(f"Rank {i}: {strategy_name}")
        print(f"  File: {filename}")
        if file_path and file_path.exists():
            print(f"  Status: ✅ File exists at {file_path}")
        else:
            print(f"  Status: ❌ File not found")
        print(f"  Score: {entry.get('score', 'N/A')}")
        print()
else:
    print("Rankings file not found!")

print("=" * 80)
print("TO DEPLOY:")
print("1. Wait for login rate limit to clear (60+ minutes)")
print("2. OR use web UI at http://127.0.0.1:5001/python")
print("3. Upload strategies manually via 'Add Strategy' button")
print("4. Start them using the 'Start' button")
print("=" * 80)
