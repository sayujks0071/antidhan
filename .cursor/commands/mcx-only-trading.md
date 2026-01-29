# MCX-only trading

Login via browser and run only MCX strategies. Use when you want to trade MCX commodities only and disable NSE/equity strategies.

## 1. Start OpenAlgo (if not running)

```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
FLASK_PORT=5001 uv run python app.py
# Or with your venv: source /path/to/venv/bin/activate && FLASK_PORT=5001 python app.py
```

Check: `lsof -i :5001`

## 2. Login in browser

- **Login**: http://127.0.0.1:5001/auth/login  
  Enter your OpenAlgo username/password and submit.
- **Broker (Kite)**: http://127.0.0.1:5001/auth/broker  
  Click "Reconnect Zerodha" if needed and complete the OAuth flow so MCX orders can go through.

## 3. Strategy page – MCX only

- Open: http://127.0.0.1:5001/python

**Stop (disable) non-MCX strategies:**

- Any **NIFTY**, **BANKNIFTY**, or **equity** strategy → click **Stop**.
- Examples to stop if present: Advanced ML Momentum, AI Hybrid Reversion Breakout, SuperTrend VWAP (when they trade NSE).

**Start (enable) only MCX strategies:**

- **MCX Global Arbitrage**
- **MCX Commodity Momentum**
- **MCX Advanced Strategy** / **MCX Advanced Momentum**
- **MCX Elite** / **MCX Neural** / **MCX Quantum** / **MCX AI Enhanced**
- **MCX Clawdbot**
- **Crude Oil** / **Natural Gas** strategies (if they use MCX)

Confirm each MCX strategy shows a **Running** (green) badge.

## 4. Verify

- **Positions**: http://127.0.0.1:5001/dashboard or `/positions` — filter for MCX symbols (GOLDM, SILVERM, CRUDEOIL, etc.).
- **Logs**: `tail -f openalgo/strategies/logs/mcx*.log` or `openalgo/log/strategies/mcx*.log`.

## MCX strategy scripts (reference)

- `mcx_global_arbitrage_strategy.py`
- `mcx_commodity_momentum_strategy.py`
- `mcx_advanced_strategy.py` / `mcx_advanced_momentum_strategy.py`
- `mcx_elite_strategy.py`, `mcx_neural_strategy.py`, `mcx_quantum_strategy.py`, `mcx_ai_enhanced_strategy.py`
- `mcx_clawdbot_strategy.py`
- `crude_oil_enhanced_strategy.py`, `crude_oil_clawdbot_strategy.py`, `natural_gas_clawdbot_strategy.py`
