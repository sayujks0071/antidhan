# Dhan Broker Setup Guide for Port 5002
**Generated**: January 28, 2026

---

## 📋 Overview

This guide helps you:
1. Configure Dhan broker credentials
2. Start OpenAlgo on port 5002 (separate from port 5001)
3. Login to Dhan via OpenAlgo
4. Start option strategies

---

## 🔑 Dhan Credentials

**Client ID**: `1105009139`  
**API Key**: `df1da5de`  
**API Secret**: `fddc233a-a819-4e40-a282-1acbf9cd70b9`  
**Application Name**: `dhan_api`

---

## 🚀 Quick Start

### Step 1: Setup Dhan Configuration

```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
chmod +x scripts/setup_dhan_port5002.sh
./scripts/setup_dhan_port5002.sh
```

This creates `.env.dhan` file with Dhan broker configuration.

### Step 2: Start OpenAlgo on Port 5002

```bash
chmod +x scripts/start_dhan_openalgo.sh
./scripts/start_dhan_openalgo.sh
```

**OR manually:**
```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
source .env.dhan && export $(cat .env.dhan | grep -v '^#' | xargs)
python3 app.py
```

**Expected Output:**
```
🚀 Starting OpenAlgo on port 5002...
Web UI: http://127.0.0.1:5002
```

### Step 3: Login to Dhan

1. **Open Web UI**: http://127.0.0.1:5002
2. **Navigate to**: Broker Login → Dhan
3. **Complete OAuth Flow**:
   - Click "Login with Dhan"
   - Authorize the application
   - You'll be redirected back with access token
4. **Verify Login**: Check "Broker Status" shows "Connected"

### Step 4: Start Option Strategies

```bash
chmod +x scripts/start_option_strategies.sh
export OPENALGO_APIKEY="your_api_key_here"  # Get from Web UI → API Keys
./scripts/start_option_strategies.sh
```

**OR via Web UI:**
1. Go to: http://127.0.0.1:5002/python
2. Find: `advanced_options_ranker`
3. Click: "Start"
4. Set environment variables if needed:
   - `OPENALGO_HOST=http://127.0.0.1:5002`
   - `OPENALGO_APIKEY=your_api_key`

---

## 📊 Available Option Strategies

### 1. Advanced Options Ranker
- **File**: `strategies/scripts/advanced_options_ranker.py`
- **Purpose**: Daily options strategy analysis & ranking
- **Indices**: NIFTY, BANKNIFTY, SENSEX
- **Features**:
  - Multi-factor analysis
  - Greeks calculation
  - Max pain calculation
  - PCR analysis
  - Strategy recommendations

---

## 🔧 Configuration Details

### Environment Variables (.env.dhan)

```bash
# Dhan Broker Credentials
BROKER_API_KEY='1105009139:::df1da5de'  # client_id:::api_key format
BROKER_API_SECRET='fddc233a-a819-4e40-a282-1acbf9cd70b9'

# Port Configuration
FLASK_PORT='5002'
FLASK_HOST_IP='127.0.0.1'

# Redirect URL for OAuth
REDIRECT_URL='http://127.0.0.1:5002/dhan/callback'

# Separate Database for Dhan Instance
DATABASE_URL='sqlite:///db/openalgo_dhan.db'
```

### Port Summary

- **Port 5001**: OpenAlgo + KiteConnect (NSE/MCX strategies)
- **Port 5002**: OpenAlgo + Dhan (Options strategies)
- **WebSocket 8765**: Port 5001 instance
- **WebSocket 8766**: Port 5002 instance

---

## 🐛 Troubleshooting

### Port Already in Use

```bash
# Check what's using port 5002
lsof -i :5002

# Kill the process
lsof -ti:5002 | xargs kill -9
```

### Dhan Login Fails

1. **Check Credentials**: Verify Client ID, API Key, API Secret
2. **Check Redirect URL**: Must match `.env.dhan` (`http://127.0.0.1:5002/dhan/callback`)
3. **Check OAuth App**: Ensure app is approved in Dhan dashboard
4. **Check Logs**: `tail -f log/app.log`

### Option Strategies Not Starting

1. **Check OpenAlgo Running**: `curl http://127.0.0.1:5002/api/v1/ping`
2. **Check API Key**: Verify `OPENALGO_APIKEY` is set correctly
3. **Check Logs**: `tail -f log/strategies/advanced_options_ranker.log`
4. **Check Dhan Login**: Ensure broker is connected

### Strategies Can't Connect to API

1. **Verify API Host**: Strategies should use `http://127.0.0.1:5002`
2. **Check API Key**: Must be valid OpenAlgo API key (not broker API key)
3. **Check Environment**: Ensure `OPENALGO_HOST` and `OPENALGO_APIKEY` are set

---

## 📝 Manual Steps (Alternative)

### 1. Create .env.dhan Manually

```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
cat > .env.dhan << 'EOF'
BROKER_API_KEY='1105009139:::df1da5de'
BROKER_API_SECRET='fddc233a-a819-4e40-a282-1acbf9cd70b9'
FLASK_PORT='5002'
FLASK_HOST_IP='127.0.0.1'
REDIRECT_URL='http://127.0.0.1:5002/dhan/callback'
DATABASE_URL='sqlite:///db/openalgo_dhan.db'
EOF
```

### 2. Start OpenAlgo Manually

```bash
export $(cat .env.dhan | grep -v '^#' | xargs)
python3 app.py
```

### 3. Start Option Strategy Manually

```bash
cd strategies/scripts
export OPENALGO_HOST="http://127.0.0.1:5002"
export OPENALGO_APIKEY="your_api_key"
python3 advanced_options_ranker.py
```

---

## ✅ Verification Checklist

- [ ] `.env.dhan` file created with correct credentials
- [ ] OpenAlgo running on port 5002
- [ ] Web UI accessible at http://127.0.0.1:5002
- [ ] Dhan broker logged in (check Broker Status)
- [ ] Option strategies can access API (check logs)
- [ ] Strategies generating signals/orders

---

## 📚 Additional Resources

- **OpenAlgo Docs**: `openalgo/docs/`
- **Dhan API Docs**: https://dhan.co/api-docs
- **Option Strategy**: `strategies/scripts/advanced_options_ranker.py`
- **Main README**: `README.md` (Dual Instance Setup)

---

**Status**: ✅ Setup scripts created, ready to use
