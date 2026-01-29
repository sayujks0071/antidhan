# Dhan Setup Quick Start
**Date**: January 28, 2026

---

## ✅ Setup Complete!

Dhan broker configuration is ready for port 5002.

---

## 🚀 Next Steps (3 Simple Commands)

### 1. Start OpenAlgo on Port 5002

```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
./scripts/start_dhan_openalgo.sh
```

**OR manually:**
```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
export $(cat .env.dhan | grep -v '^#' | xargs)
python3 app.py
```

**Expected**: OpenAlgo starts on http://127.0.0.1:5002

---

### 2. Login to Dhan

1. **Open**: http://127.0.0.1:5002
2. **Go to**: Broker Login → Dhan
3. **Click**: "Login with Dhan"
4. **Authorize**: Complete OAuth flow
5. **Verify**: Check "Broker Status" shows "Connected"

---

### 3. Start Option Strategies

**Via Script:**
```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
export OPENALGO_APIKEY="your_api_key"  # Get from Web UI → API Keys
./scripts/start_option_strategies.sh
```

**Via Web UI:**
1. Go to: http://127.0.0.1:5002/python
2. Find: `advanced_options_ranker`
3. Click: "Start"
4. Set environment variables:
   - `OPENALGO_HOST=http://127.0.0.1:5002`
   - `OPENALGO_APIKEY=your_api_key`

---

## 📋 Configuration Summary

**Dhan Credentials**:
- Client ID: `1105009139`
- API Key: `df1da5de`
- API Secret: `fddc233a-a819-4e40-a282-1acbf9cd70b9`

**Ports**:
- **5001**: KiteConnect (NSE/MCX) - Already running
- **5002**: Dhan (Options) - **Start this one**

**Files Created**:
- `.env.dhan` - Dhan broker configuration
- `scripts/setup_dhan_port5002.sh` - Setup script
- `scripts/start_dhan_openalgo.sh` - Start script
- `scripts/start_option_strategies.sh` - Strategy starter

---

## 📊 Available Option Strategies

1. **Advanced Options Ranker** (`advanced_options_ranker.py`)
   - Analyzes NIFTY, BANKNIFTY, SENSEX
   - Calculates Greeks, Max Pain, PCR
   - Generates strategy recommendations

---

## 🐛 Troubleshooting

### Port 5002 Already in Use
```bash
lsof -ti:5002 | xargs kill -9
```

### Can't Login to Dhan
- Check credentials in `.env.dhan`
- Verify redirect URL: `http://127.0.0.1:5002/dhan/callback`
- Check logs: `tail -f log/app.log`

### Strategies Not Starting
- Verify OpenAlgo running: `curl http://127.0.0.1:5002/api/v1/ping`
- Check API key is set correctly
- Check logs: `tail -f log/strategies/advanced_options_ranker.log`

---

## 📚 Full Documentation

See `DHAN_SETUP_GUIDE.md` for detailed instructions.

---

**Status**: ✅ Ready to start!
