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
    # Simulate High Rejection Rate (> 70%) to trigger threshold lowering
    # Signals: 100, Entries: 20, Rejected: 80
    content = []
    content.append("2024-10-24 09:15:00 - VWAP_RELIANCE - INFO - Starting SuperTrend VWAP")

    # Generate rejections
    for i in range(80):
        content.append(f"2024-10-24 10:{i%60:02d}:00 - VWAP_RELIANCE - INFO - [REJECTED] symbol=RELIANCE score={random.uniform(1.0, 1.4):.2f} reason=Threshold")

    # Generate entries
    for i in range(20):
        content.append(f"2024-10-24 11:{i%60:02d}:00 - VWAP_RELIANCE - INFO - [ENTRY] Buy order placed")

    # Metrics line
    content.append(f"2024-10-24 15:30:00 - VWAP_RELIANCE - INFO - [METRICS] signals=100 entries=20 exits=20 rejected=80 errors=0 pnl=500.0")

    write_log("supertrend_vwap_strategy", "\n".join(content))

def generate_momentum_log():
    # Simulate Low R:R (< 1.5) to trigger stop tightening
    # Wins: 10, Losses: 10. Avg Win: 100, Avg Loss: 80. R:R = 1.25
    content = []
    content.append("2024-10-24 09:15:00 - Momentum_RELIANCE - INFO - Starting Momentum Strategy")

    # Generate trades
    total_pnl = 0
    for i in range(10):
        win = 100
        loss = -80
        total_pnl += win + loss
        content.append(f"2024-10-24 10:{i*2:02d}:00 - Momentum_RELIANCE - INFO - [EXIT] symbol=RELIANCE pnl={win}")
        content.append(f"2024-10-24 11:{i*2:02d}:00 - Momentum_RELIANCE - INFO - [EXIT] symbol=RELIANCE pnl={loss}")

    # Metrics line
    # Signals=40, Entries=20, Exits=20, Rejected=20
    content.append(f"2024-10-24 15:30:00 - Momentum_RELIANCE - INFO - [METRICS] signals=40 entries=20 exits=20 rejected=20 errors=0 pnl={total_pnl}")

    write_log("advanced_ml_momentum_strategy", "\n".join(content))

if __name__ == "__main__":
    os.makedirs(LOG_DIR, exist_ok=True)
    generate_vwap_log()
    generate_momentum_log()
