import json
import os

config_path = "openalgo/strategies/strategy_configs.json"

with open(config_path, "r") as f:
    config = json.load(f)

config["NSE_MOMENTUM_STRATEGY"] = {
  "id": "NSE_MOMENTUM_STRATEGY",
  "name": "NSE Momentum Strategy",
  "description": "NSE Momentum Strategy using RSI and Bollinger Bands",
  "file_path": "strategies/scripts/nse_momentum_strategy.py",
  "user_id": "testuser",
  "created_at": "2026-03-01T10:00:00",
  "symbol": "RELIANCE",
  "schedule_enabled": True,
  "schedule_days": ["mon", "tue", "wed", "thu", "fri"],
  "params": {
    "rsi_period": 14,
    "bb_period": 20,
    "bb_std": 2.0,
    "quantity": 1
  },
  "is_running": False,
  "is_scheduled": True,
  "schedule_start": "09:15",
  "schedule_stop": "15:30"
}

with open(config_path, "w") as f:
    json.dump(config, f, indent=2)

print("Updated config successfully.")
