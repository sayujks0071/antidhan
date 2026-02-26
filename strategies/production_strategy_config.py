#!/usr/bin/env python3
"""
OpenAlgo Strategy Manager - Production Configuration
=====================================================
Target: ₹50,000 profit per day
Max Loss: ₹10,000 per day
Risk Management: Strict stop-losses and position sizing

This configuration manages risk across Equity, F&O, and MCX segments.
"""

import os

# =============================================================================
# RISK MANAGEMENT CONFIGURATION (MOST IMPORTANT)
# =============================================================================

RISK_CONFIG = {
    # Daily Limits
    "MAX_DAILY_LOSS": 10000,  # ₹10,000 max loss per day
    "DAILY_PROFIT_TARGET": 50000,  # ₹50,000 target profit
    # Position Sizing
    "MAX_POSITION_SIZE_PER_TRADE": 50000,  # Max ₹50,000 per trade
    "DEFAULT_POSITION_SIZE": 25000,  # Default ₹25,000 per trade
    # Stop Loss Configuration
    "EQUITY_STOP_LOSS_PERCENT": 1.5,  # 1.5% stop loss for equity
    "OPTIONS_STOP_LOSS_PERCENT": 50,  # 50% stop loss for options (premium based)
    "MCX_STOP_LOSS_PERCENT": 0.20,  # 2% stop loss for commodities
    # Profit Taking
    "TAKE_PROFIT_PERCENT": 3.0,  # 3% profit target for equity
    "OPTIONS_TAKE_PROFIT_PERCENT": 100,  # 100% (double) for options
    "MCX_TAKE_PROFIT_PERCENT": 4.0,  # 4% profit target for commodities
    # Trailing Stop
    "USE_TRAILING_STOP": True,
    "TRAILING_STOP_PERCENT": 1.0,  # 1% trailing stop
    # Time-based Exit
    "SQUARE_OFF_TIME": "15:10",  # Square off at 3:10 PM
    "ALLOW_TODAY_TRADES_AFTER": "09:15",  # Allow trades after 9:15 AM
    "AVOID_TRADES_BEFORE": "15:00",  # No new trades after 3 PM
}

# =============================================================================
# SEGMENT-SPECIFIC CONFIGURATION
# =============================================================================

SEGMENT_CONFIGS = {
    "EQUITY": {
        "enabled": True,
        "instruments": [
            "RELIANCE",
            "TCS",
            "INFY",
            "HDFCBANK",
            "ICICIBANK",
            "SBIN",
            "LT",
            "AXISBANK",
            "KOTAKBANK",
            "ADANIPORTS",
        ],
        "max_trades_per_day": 20,
        "position_size": 60000,  # aggressive sizing
        "stop_loss_percent": 1.5,
        "take_profit_percent": 3.0,
        "timeframe": "15min",
        "api_interval": "1minute",
    },
    "FNO_OPTIONS": {
        "enabled": True,
        "instruments": {
            "BANKNIFTY": {
                "strike_range": 10,  # ±10 strikes from ATM
                "expiry": "weekly",
                "option_type": "CE",  # Buy CE for uptrend, PE for downtrend
                "lot_size": 30,
                "max_order_quantity": 120,  # 4 lots max
            },
            "NIFTY": {
                "strike_range": 10,
                "expiry": "weekly",
                "option_type": "CE",
                "lot_size": 65,
                "max_order_quantity": 130,  # 2 lots max
            },
        },
        "max_trades_per_day": 40,
        "position_size": 140000,  # concentrated aggressive sizing
        "max_order_quantity": 130,  # fallback cap if instrument-specific cap not provided
        "stop_loss_percent": 50,  # 50% of premium
        "take_profit_percent": 100,  # 100% (2x) profit target
        "api_interval": "1minute",
    },
    "MCX": {
        "enabled": True,
        "instruments": {
            "CRUDEOIL": {
                "exchange": "MCX",
                "lot_size": 100,  # 100 barrels
                "tick_size": 1,
            },
            "GOLD": {
                "exchange": "MCX",
                "lot_size": 1,  # 1 kg
                "tick_size": 1,
            },
            "SILVER": {
                "exchange": "MCX",
                "lot_size": 1,  # 1 kg
                "tick_size": 1,
            },
            "NATURALGAS": {
                "exchange": "MCX",
                "lot_size": 1250,  # 1250 mmBtu
                "tick_size": 0.3,
            },
        },
        "max_trades_per_day": 12,
        "position_size": 70000,
        "stop_loss_percent": 2.0,
        "take_profit_percent": 4.0,
        "api_interval": "1minute",
    },
}

# =============================================================================
# STRATEGY PARAMETERS
# =============================================================================

STRATEGY_PARAMS = {
    # Entry trigger (price momentum from previous loop).
    # Lower value => more frequent entries.
    "MOMENTUM_ENTRY_PERCENT": 0.03,
    # Aggressive mode: place this many bootstrap BUY trades per segment
    # on first valid quotes before momentum comparison is available.
    "AGGRESSIVE_BOOTSTRAP_TRADES": 2,
    "FNO_ACCEPTED_ONLY": True,
    "AGGRESSIVE_FORCE_START_LOOPS": 4,
    "ALLOW_BLIND_START_ENTRIES": True,
    "BLIND_ENTRY_FALLBACK_PRICE": 250.0,
    # Trend Following Parameters
    "EMA_FAST": 9,
    "EMA_SLOW": 21,
    "RSI_PERIOD": 14,
    "RSI_OVERBOUGHT": 70,
    "RSI_OVERSOLD": 30,
    "ATR_PERIOD": 14,
    "ATR_MULTIPLIER": 2.0,  # For stop loss
    # Confirmation Indicators
    "USE_MACD": True,
    "MACD_FAST": 12,
    "MACD_SLOW": 26,
    "MACD_SIGNAL": 9,
    "USE_SUPERTREND": True,
    "SUPERTREND_PERIOD": 10,
    "SUPERTREND_MULTIPLIER": 3,
    # Volume Confirmation
    "MIN_VOLUME_MULTIPLIER": 1.5,
    # Market Hours (IST)
    "MARKET_OPEN": "09:15",
    "MARKET_CLOSE": "15:30",
    "PRE_MARKET_START": "09:00",
}

# =============================================================================
# TRADING SESSION CONFIGURATION
# =============================================================================

SESSION_CONFIG = {
    "session_type": "live",  # live, paper, backtest
    "broker": "dhan",
    # API Configuration
    "api_host": os.getenv("HOST_SERVER", "https://algo.endoscopicspinehyderabad.in"),
    "api_key": os.getenv("OPENALGO_API_KEY", os.getenv("BROKER_API_KEY", "490de1b5")),
    # WebSocket for real-time updates
    "use_websocket": True,
    "websocket_reconnect": True,
    # Order Configuration
    "ORDER_TYPE": "MARKET",  # MARKET, LIMIT
    "PRODUCT_TYPE": "MIS",  # Must be one of MIS, NRML, CNC for OpenAlgo order APIs
    "VALIDITY": "DAY",  # DAY, IOC
    # Retry Configuration
    "max_order_retries": 3,
    "retry_delay_seconds": 2,
}

# =============================================================================
# FILTERS AND CONDITIONS
# =============================================================================

FILTER_CONFIG = {
    # Minimum criteria to enter a trade
    "MIN_VOLUME": 500000,  # ₹5 Lakhs minimum volume
    "MIN_PRICE": 50,  # Min stock price ₹50
    "MAX_PRICE": 5000,  # Max stock price ₹5000
    # Volatility Filter
    "MAX_ATR_PERCENT": 5.0,  # Max 5% ATR for entry
    "MIN_ATR_PERCENT": 0.5,  # Min 0.5% ATR for movement
    # Time Filters
    "AVOID_OPENING_HOUR": False,  # Don't trade first 15 min
    "AVOID_CLOSING_HOUR": True,  # Avoid last 30 min
    "BEST_TRADING_HOURS": ["10:00-12:00", "14:00-15:00"],
    # Gap Up/Down Filter
    "MAX_GAP_PERCENT": 3.0,  # Max 3% gap
}

# =============================================================================
# DASHBOARD CONFIGURATION (for monitoring)
# =============================================================================

DASHBOARD_CONFIG = {
    "display_positions": True,
    "display_pnl": True,
    "display_daily_stats": True,
    "alert_on_loss": True,
    "alert_on_target": True,
    "telegram_alerts": False,  # Set True and add token if needed
    "email_alerts": False,
}


def get_config_summary():
    """Returns a summary of the configuration"""
    return {
        "target_profit": f"₹{RISK_CONFIG['DAILY_PROFIT_TARGET']:,}",
        "max_loss": f"₹{RISK_CONFIG['MAX_DAILY_LOSS']:,}",
        "risk_reward_ratio": RISK_CONFIG["DAILY_PROFIT_TARGET"]
        / RISK_CONFIG["MAX_DAILY_LOSS"],
        "segments": list(SEGMENT_CONFIGS.keys()),
        "broker": SESSION_CONFIG["broker"],
        "mode": SESSION_CONFIG["session_type"],
    }


if __name__ == "__main__":
    print("=" * 60)
    print("OpenAlgo Strategy Configuration")
    print("=" * 60)
    config = get_config_summary()
    print(f"\n📊 Target Profit: {config['target_profit']}")
    print(f"🛡️ Max Daily Loss: {config['max_loss']}")
    print(f"📈 Risk:Reward Ratio: 1:{config['risk_reward_ratio']}")
    print(f"📱 Trading Segments: {', '.join(config['segments'])}")
    print(f"🔧 Broker: {config['broker']}")
    print(f"🎯 Mode: {config['mode']}")
    print("\n" + "=" * 60)
    print("Configuration is ready for deployment!")
    print("=" * 60)
