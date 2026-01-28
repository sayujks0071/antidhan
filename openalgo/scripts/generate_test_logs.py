import os
from datetime import datetime
import random

LOG_DIR = "openalgo/log/strategies"
DATE_STR = datetime.now().strftime("%Y%m%d")

def write_log(strategy_name, content):
    filename = f"{strategy_name}_{DATE_STR}.log"
    filepath = os.path.join(LOG_DIR, filename)
    with open(filepath, 'w') as f:
        f.write(content)
    print(f"Generated {filepath}")

def generate_vwap_log():
    # Simulate Low Win Rate (< 60%) AND Low R:R (< 1.5)
    # Target: Trigger "Tighten Filters" (Increase Threshold) AND "Tighten Stop"

    # Metrics:
    # Signals: 20
    # Entries: 20
    # Rejected: 0 (Rejection Rate 0%, so no conflict with Threshold Tuning)
    # Wins: 8 (40% WR < 60%)
    # Losses: 12
    # Avg Win: 100
    # Avg Loss: 100
    # R:R: 1.0 (< 1.5)

    content = []
    timestamp = datetime.now().strftime("%Y-%m-%d")
    content.append(f"{timestamp} 09:15:00 - VWAP_RELIANCE - INFO - Starting SuperTrend VWAP")

    total_pnl = 0
    total_win_pnl = 0
    total_loss_pnl = 0

    # Generate 20 trades
    for i in range(20):
        # Entry
        content.append(f"{timestamp} 10:{i:02d}:00 - VWAP_RELIANCE - INFO - [ENTRY] Buy order placed")

        if i < 8: # 8 Wins
            pnl = 100.0
            total_win_pnl += pnl
        else: # 12 Losses
            pnl = -100.0
            total_loss_pnl += abs(pnl)

        total_pnl += pnl
        content.append(f"{timestamp} 10:{i:02d}:30 - VWAP_RELIANCE - INFO - [EXIT] symbol=RELIANCE pnl={pnl}")

    # Metrics line
    # Note: parsing logic in perform_eod_optimization.py looks for [METRICS] ...
    # It aggregates pnl, win_pnl etc from individual lines or the METRICS line?
    # parse_log_file reads METRICS line for summary counts.
    # It reads [EXIT] lines for wins/losses/pnl calculations.
    # So the METRICS line counts must match.

    content.append(f"{timestamp} 15:30:00 - VWAP_RELIANCE - INFO - [METRICS] signals=20 entries=20 exits=20 rejected=0 errors=0 pnl={total_pnl}")

    write_log("supertrend_vwap_strategy", "\n".join(content))

def generate_momentum_log():
    # Use existing logic but update timestamp
    content = []
    timestamp = datetime.now().strftime("%Y-%m-%d")
    content.append(f"{timestamp} 09:15:00 - Momentum_RELIANCE - INFO - Starting Momentum Strategy")

    # Generate trades
    total_pnl = 0
    for i in range(10):
        win = 100
        loss = -80
        total_pnl += win + loss
        content.append(f"{timestamp} 10:{i*2:02d}:00 - Momentum_RELIANCE - INFO - [EXIT] symbol=RELIANCE pnl={win}")
        content.append(f"{timestamp} 11:{i*2:02d}:00 - Momentum_RELIANCE - INFO - [EXIT] symbol=RELIANCE pnl={loss}")

    # Metrics line
    content.append(f"{timestamp} 15:30:00 - Momentum_RELIANCE - INFO - [METRICS] signals=40 entries=20 exits=20 rejected=20 errors=0 pnl={total_pnl}")

    write_log("advanced_ml_momentum_strategy", "\n".join(content))

if __name__ == "__main__":
    os.makedirs(LOG_DIR, exist_ok=True)
    generate_vwap_log()
    generate_momentum_log()
