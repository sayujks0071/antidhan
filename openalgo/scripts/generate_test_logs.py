import os
from datetime import datetime
import random

# Target directory matches perform_eod_optimization.py LOG_DIRS[0]
LOG_DIR = "openalgo/strategies/logs"
DATE_STR = datetime.now().strftime("%Y%m%d")

def write_log(strategy_name, content):
    # Ensure directory exists
    os.makedirs(LOG_DIR, exist_ok=True)
    filename = f"{strategy_name}_{DATE_STR}.log"
    filepath = os.path.join(LOG_DIR, filename)
    with open(filepath, 'w') as f:
        f.write(content)
    print(f"Generated {filepath}")

def generate_vwap_log():
    """
    Simulates:
    1. Low Win Rate (< 60%): 40% WR (8 wins, 12 losses)
    2. Low R:R (< 1.5): Avg Win 100, Avg Loss 100 -> R:R 1.0

    Expected Actions:
    - Increase threshold (Tighten filters)
    - Decrease stop_pct (Tighten stop)
    """
    content = []
    timestamp = datetime.now().strftime("%Y-%m-%d")
    content.append(f"{timestamp} 09:15:00 - VWAP_RELIANCE - INFO - Starting SuperTrend VWAP")

    total_pnl = 0
    total_win_pnl = 0
    total_loss_pnl = 0
    wins = 0
    losses = 0

    # Generate 20 trades
    for i in range(20):
        content.append(f"{timestamp} 10:{i:02d}:00 - VWAP_RELIANCE - INFO - [ENTRY] symbol=RELIANCE entry=1000.0 order_id=100{i}")

        # 8 Wins (40%)
        if i < 8:
            pnl = 100.0
            total_win_pnl += pnl
            wins += 1
        else: # 12 Losses
            pnl = -100.0
            total_loss_pnl += abs(pnl)
            losses += 1

        total_pnl += pnl
        content.append(f"{timestamp} 10:{i:02d}:30 - VWAP_RELIANCE - INFO - [EXIT] symbol=RELIANCE pnl={pnl}")

    # Metrics line
    # signals=20, entries=20, exits=20, rejected=0, errors=0
    content.append(f"{timestamp} 15:30:00 - VWAP_RELIANCE - INFO - [METRICS] signals=20 entries=20 exits=20 rejected=0 errors=0 pnl={total_pnl}")

    write_log("supertrend_vwap_strategy", "\n".join(content))

def generate_rejection_log():
    """
    Simulates:
    1. High Rejection Rate (> 70%): 100 signals, 80 rejected.

    Expected Actions:
    - Decrease threshold (Lower entry barrier)
    """
    content = []
    timestamp = datetime.now().strftime("%Y-%m-%d")
    content.append(f"{timestamp} 09:15:00 - Momentum_TATA - INFO - Starting Momentum Strategy")

    # Generate 80 rejections
    for i in range(80):
         content.append(f"{timestamp} 09:{i%60:02d}:00 - Momentum_TATA - INFO - [REJECTED] symbol=TATASTEEL score=65 reason=Threshold_Not_Met")

    # Generate 20 entries (10 wins, 10 losses, decent R:R to isolate rejection tuning)
    total_pnl = 0
    for i in range(20):
        content.append(f"{timestamp} 10:{i:02d}:00 - Momentum_TATA - INFO - [ENTRY] symbol=TATASTEEL entry=150.0")

        if i % 2 == 0:
            pnl = 200.0 # Good win
        else:
            pnl = -100.0 # Small loss

        total_pnl += pnl
        content.append(f"{timestamp} 10:{i:02d}:30 - Momentum_TATA - INFO - [EXIT] symbol=TATASTEEL pnl={pnl}")

    # Metrics line
    # signals=100 (80 rejected + 20 entries), entries=20, exits=20
    content.append(f"{timestamp} 15:30:00 - Momentum_TATA - INFO - [METRICS] signals=100 entries=20 exits=20 rejected=80 errors=0 pnl={total_pnl}")

    write_log("advanced_ml_momentum_strategy", "\n".join(content))

if __name__ == "__main__":
    generate_vwap_log()
    generate_rejection_log()
