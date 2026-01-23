# Strategy Management Scripts Guide

## Overview

Four scripts have been created to manage OpenAlgo strategies:

1. **manage_strategies.py** - Comprehensive management (all-in-one)
2. **restart_strategies.py** - Restart specific strategies
3. **set_all_api_keys.py** - Set API keys for all strategies
4. **check_strategy_status.py** - Enhanced status check

## Quick Start

### Check Current Status
```bash
cd /Users/mac/dyad-apps/openalgo
python3 scripts/check_strategy_status.py
```

### Set API Keys for All Strategies
```bash
cd /Users/mac/dyad-apps/openalgo
source venv/bin/activate
export OPENALGO_USERNAME="YOUR_OPENALGO_USERNAME"
export OPENALGO_PASSWORD="YOUR_OPENALGO_PASSWORD"
python3 scripts/set_all_api_keys.py
```

### Restart Specific Strategies
```bash
cd /Users/mac/dyad-apps/openalgo
source venv/bin/activate
export OPENALGO_USERNAME="YOUR_OPENALGO_USERNAME"
export OPENALGO_PASSWORD="YOUR_OPENALGO_PASSWORD"
python3 scripts/restart_strategies.py --strategies orb_strategy trend_pullback_strategy
```

### Comprehensive Management (All Tasks)
```bash
cd /Users/mac/dyad-apps/openalgo
source venv/bin/activate
export OPENALGO_USERNAME="YOUR_OPENALGO_USERNAME"
export OPENALGO_PASSWORD="YOUR_OPENALGO_PASSWORD"
export OPENALGO_APIKEY="YOUR_OPENALGO_APIKEY"
python3 scripts/manage_strategies.py
```

## Script Details

### 1. check_strategy_status.py
**Purpose:** View current status of all strategies

**Features:**
- Lists all strategies (running and stopped)
- Shows API key status
- Identifies strategies needing restart (bug fixes)
- Shows recent errors from logs

**Usage:**
```bash
python3 scripts/check_strategy_status.py
```

**No authentication required** - reads config files directly

### 2. set_all_api_keys.py
**Purpose:** Set OPENALGO_APIKEY for all strategies that don't have it

**Features:**
- Identifies strategies without API keys
- Stops running strategies temporarily
- Sets API key via API endpoint
- Restarts strategies that were running

**Usage:**
```bash
export OPENALGO_USERNAME="your_username"
export OPENALGO_PASSWORD="your_password"
export OPENALGO_APIKEY="your_api_key"
python3 scripts/set_all_api_keys.py
```

### 3. restart_strategies.py
**Purpose:** Restart specific strategies (useful after bug fixes)

**Features:**
- Stops specified strategies
- Waits for process termination
- Starts strategies again
- Verifies restart success

**Usage:**
```bash
# Restart specific strategies
python3 scripts/restart_strategies.py --strategies orb_strategy trend_pullback_strategy

# Restart default strategies (ORB, Trend Pullback)
python3 scripts/restart_strategies.py
```

**Environment Variables:**
- `OPENALGO_USERNAME` (set in your environment)
- `OPENALGO_PASSWORD` (set in your environment)
- `OPENALGO_BASE_URL` (default: "http://127.0.0.1:5001")

### 4. manage_strategies.py
**Purpose:** Comprehensive management - does everything

**Features:**
- Checks all strategies
- Sets API keys for strategies that need them
- Restarts strategies with bug fixes
- Handles all edge cases

**Usage:**
```bash
export OPENALGO_USERNAME="your_username"
export OPENALGO_PASSWORD="your_password"
export OPENALGO_APIKEY="your_api_key"
python3 scripts/manage_strategies.py
```

## Current Status

Based on latest check:
- **2 strategies running** (ML Momentum, SuperTrend VWAP)
- **5 strategies need API keys** (ORB, Trend Pullback, and others)
- **2 strategies need restart** (ORB, Trend Pullback - bug fixes applied)

## Recommended Workflow

1. **Check status:**
   ```bash
   python3 scripts/check_strategy_status.py
   ```

2. **Set API keys for all:**
   ```bash
   python3 scripts/set_all_api_keys.py
   ```

3. **Restart strategies with bug fixes:**
   ```bash
   python3 scripts/restart_strategies.py --strategies orb_strategy trend_pullback_strategy
   ```

4. **Or use comprehensive script (does all above):**
   ```bash
   python3 scripts/manage_strategies.py
   ```

## Error Handling

All scripts handle:
- Rate limiting (waits and retries)
- Session expiration (re-login)
- Process management (checks PID)
- API errors (graceful failure with messages)

## Notes

- Scripts require OpenAlgo server to be running on port 5001
- CSRF tokens are automatically fetched
- Strategies must be stopped before setting environment variables
- Process status is verified using `ps` command
