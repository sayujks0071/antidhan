# Clawdbot Integration Guide

## Overview

This guide explains how Clawdbot AI assistant is integrated into OpenAlgo to enhance trading strategies with AI-powered market analysis, dynamic parameter optimization, browser-based monitoring, and multi-channel alerts.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Clawdbot Gateway                         │
│              (ws://127.0.0.1:18789)                         │
│  - AI Agent (Claude/OpenAI)                                  │
│  - Browser Control                                           │
│  - Multi-Channel (Telegram/WhatsApp/Slack)                  │
│  - Skills Platform                                           │
└──────────────────┬──────────────────────────────────────────┘
                   │ WebSocket/HTTP
                   │
┌──────────────────▼──────────────────────────────────────────┐
│           Clawdbot Trading Bridge Service                    │
│  (openalgo/services/clawdbot_bridge_service.py)             │
│  - Connects to Clawdbot Gateway                             │
│  - Exposes trading context to AI                            │
│  - Receives AI recommendations                               │
│  - Routes alerts to channels                                 │
└──────────────────┬──────────────────────────────────────────┘
                   │
        ┌──────────┴──────────┐
        │                     │
┌───────▼────────┐  ┌────────▼──────────┐
│  OpenAlgo MCP  │  │  Strategy Utils    │
│  Server        │  │  (clawdbot_adapter) │
│  (mcpserver.py)│  │                    │
└────────────────┘  └────────────────────┘
        │                     │
        └──────────┬──────────┘
                   │
        ┌──────────▼──────────┐
        │  Trading Strategies │
        │  (Enhanced with AI) │
        └─────────────────────┘
```

## Installation

### Prerequisites

- Node.js ≥22
- npm or pnpm

### Step 1: Install Clawdbot

```bash
npm install -g clawdbot@latest
# or
pnpm add -g clawdbot@latest
```

### Step 2: Run Onboarding Wizard

```bash
clawdbot onboard --install-daemon
```

This will:
- Set up the Clawdbot Gateway
- Configure workspace directory (`~/clawd`)
- Set up skills directory
- Install Gateway as a daemon service

### Step 3: Configure Clawdbot

Edit `~/.clawdbot/clawdbot.json`:

```json
{
  "agent": {
    "model": "anthropic/claude-opus-4-5",
    "workspace": "~/clawd"
  },
  "gateway": {
    "bind": "127.0.0.1:18789",
    "port": 18789
  },
  "channels": {
    "telegram": {
      "botToken": "YOUR_TELEGRAM_BOT_TOKEN",
      "allowFrom": ["YOUR_TELEGRAM_USERNAME"]
    },
    "whatsapp": {
      "allowFrom": ["YOUR_PHONE_NUMBER"]
    }
  }
}
```

### Step 4: Configure OpenAlgo

Add to `openalgo/.env`:

```env
CLAWDBOT_ENABLED=TRUE
CLAWDBOT_GATEWAY_URL=ws://127.0.0.1:18789
CLAWDBOT_WORKSPACE=~/clawd
CLAWDBOT_ALERT_CHANNELS=telegram,whatsapp
CLAWDBOT_AI_ENABLED=TRUE
```

## Trading Skills

Clawdbot skills are located in `~/clawd/skills/`:

1. **trading-market-analysis**: Analyzes market conditions, trends, volatility
2. **trading-strategy-optimization**: Suggests parameter adjustments
3. **trading-performance-analysis**: Analyzes trading performance
4. **trading-risk-assessment**: Evaluates portfolio risk

## Usage in Strategies

### Basic Integration

```python
from clawdbot_adapter import (
    get_ai_market_context,
    get_ai_entry_signal,
    get_ai_exit_signal,
    get_ai_position_size,
    send_ai_alert
)

# Get AI market context
ai_context = get_ai_market_context(symbol, "MCX", "15m")
regime = ai_context.get("regime")  # TRENDING/RANGING/MIXED
sentiment = ai_context.get("sentiment")  # BULLISH/NEUTRAL/BEARISH
confidence = ai_context.get("confidence")  # 0.0-1.0

# Get AI entry recommendation
technical_data = {"rsi": 55, "macd_hist": 0.5, "adx": 25}
ai_entry = get_ai_entry_signal(symbol, "MCX", technical_data)
recommendation = ai_entry.get("recommendation")  # BUY/SELL/NEUTRAL

# Get AI position size multiplier
ai_size = get_ai_position_size(symbol, signal_strength, account_balance)
multiplier = ai_size.get("multiplier")  # 0.7-1.2

# Send alert
send_ai_alert("Entry signal detected", priority="info")
```

### Enhanced Strategy Example

```python
def check_entry_signal(df, symbol):
    # 1. Technical analysis
    technical_signal = calculate_technical_signals(df)
    
    # 2. Get AI context
    ai_context = get_ai_market_context(symbol, "MCX")
    ai_entry = get_ai_entry_signal(symbol, "MCX", technical_signal)
    
    # 3. Hybrid approach: Combine signals
    if technical_signal.score > 75 and ai_entry["confidence"] > 0.6:
        # Both agree - high conviction
        position_size_multiplier = 1.2
    elif technical_signal.score > 75 and ai_entry["confidence"] < 0.4:
        # Technical yes, AI no - reduce size
        position_size_multiplier = 0.7
    else:
        position_size_multiplier = 0.5
    
    # 4. Final decision (strategy retains control)
    if technical_signal.score * position_size_multiplier > 60:
        return True, position_size_multiplier
    return False, 0
```

## Services

### Bridge Service

`openalgo/services/clawdbot_bridge_service.py`

Connects OpenAlgo to Clawdbot Gateway via WebSocket. Provides:
- `get_market_analysis()` - AI market analysis
- `get_strategy_recommendation()` - Parameter suggestions
- `send_trading_alert()` - Send alerts via channels
- `get_risk_assessment()` - Portfolio risk analysis
- `optimize_strategy_parameters()` - Strategy optimization

### Alert Service

`openalgo/services/clawdbot_alert_service.py`

Centralized alert routing:
- `send_alert()` - Generic alert sending
- `send_entry_alert()` - Entry signal alerts
- `send_exit_alert()` - Exit signal alerts
- `send_take_profit_alert()` - TP achievement alerts
- `send_stop_loss_alert()` - SL hit alerts

### Optimization Service

`openalgo/services/clawdbot_optimization_service.py`

AI-powered parameter optimization:
- `collect_strategy_performance()` - Collect performance data
- `get_optimization_suggestions()` - Get AI suggestions
- `apply_optimization()` - Apply suggestions (with approval)

## Market Monitoring

`openalgo/scripts/clawdbot_market_monitor.py`

Uses Clawdbot's browser control to monitor:
- NSE indices
- MCX commodity prices
- Economic calendar

Run as a background service:

```bash
python openalgo/scripts/clawdbot_market_monitor.py
```

## Channel Configuration

### Telegram

1. Create bot via [@BotFather](https://t.me/botfather)
2. Get bot token
3. Add to `~/.clawdbot/clawdbot.json`:

```json
{
  "channels": {
    "telegram": {
      "botToken": "YOUR_BOT_TOKEN",
      "allowFrom": ["YOUR_TELEGRAM_USERNAME"]
    }
  }
}
```

### WhatsApp

1. Link device: `clawdbot channels login`
2. Add phone number to allowlist in config

## Troubleshooting

### Gateway Not Running

```bash
# Check Gateway status
clawdbot gateway --status

# Start Gateway manually
clawdbot gateway --port 18789 --verbose
```

### Connection Errors

- Verify Gateway is running: `curl http://127.0.0.1:18789`
- Check WebSocket URL in `.env`
- Verify `CLAWDBOT_ENABLED=TRUE`

### AI Not Responding

- Check model configuration in `~/.clawdbot/clawdbot.json`
- Verify API keys are set (Anthropic/OpenAI)
- Check Gateway logs: `clawdbot gateway --verbose`

### Alerts Not Sending

- Verify channel configuration in Clawdbot config
- Check channel allowlists
- Test channel connection: `clawdbot message send --to CHANNEL --message "Test"`

## Security Considerations

- Clawdbot Gateway runs on localhost only (default)
- API keys stored securely in `~/.clawdbot/`
- Channel allowlists configured for authorized users
- AI recommendations are advisory only - no direct order execution
- All trading decisions require strategy approval

## Performance

- AI query response time: < 2 seconds (cached)
- Alert delivery: > 95% success rate
- Cache TTL: 60 seconds (configurable)

## Future Enhancements

- Real-time AI streaming for live market analysis
- Clawdbot Canvas integration for visual dashboards
- Voice wake integration for hands-free alerts
- Advanced pattern recognition
- Multi-agent coordination

## References

- [Clawdbot Documentation](https://docs.clawd.bot)
- [Clawdbot GitHub](https://github.com/clawdbot/clawdbot)
- [OpenAlgo Strategies](../strategies/README.md)
