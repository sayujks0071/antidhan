# Dhan Setup on Port 5001 - Complete Guide
**Date**: January 28, 2026

---

## ✅ Using Port 5001 for Dhan

Since port 5001 is already running, we'll use it for both Kite and Dhan brokers.

---

## 🚀 Quick Start (3 Steps)

### Step 1: Login to Dhan via Web UI

1. **Open**: http://127.0.0.1:5001
2. **Navigate to**: Broker Login → Dhan
3. **Click**: "Login with Dhan"
4. **Complete OAuth**:
   - Authorize the application
   - You'll be redirected back
5. **Verify**: Check "Broker Status" shows Dhan as "Connected"

---

### Step 2: Get OpenAlgo API Key

1. **Go to**: http://127.0.0.1:5001
2. **Navigate to**: API Keys (or Settings → API Keys)
3. **Generate/Copy** your API key
4. **Save it** - you'll need it for strategies

---

### Step 3: Start Option Strategies

**Option A - Via Web UI (Recommended)**:
1. Go to: http://127.0.0.1:5001/python
2. Find: `advanced_options_ranker`
3. Click: "Start"
4. Set environment variables:
   - `OPENALGO_HOST=http://127.0.0.1:5001`
   - `OPENALGO_APIKEY=your_api_key_here`

**Option B - Via Script**:
```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
export OPENALGO_HOST="http://127.0.0.1:5001"
export OPENALGO_APIKEY="your_api_key_here"
python3 strategies/scripts/advanced_options_ranker.py
```

---

## 📋 Dhan Credentials (Already Configured)

- **Client ID**: `1105009139`
- **API Key**: `df1da5de`
- **API Secret**: `fddc233a-a819-4e40-a282-1acbf9cd70b9`

**Note**: These are stored in `.env.dhan` but you'll login via OAuth in the Web UI.

---

## 🔧 Configuration Summary

**Port**: 5001 (same as Kite)  
**Web UI**: http://127.0.0.1:5001  
**API Endpoint**: http://127.0.0.1:5001/api/v1/  
**Option Strategy**: Points to port 5001 ✅

---

## 📊 Available Option Strategies

### Advanced Options Ranker
- **File**: `strategies/scripts/advanced_options_ranker.py`
- **Status**: ✅ Updated to use port 5001
- **Features**:
  - Analyzes NIFTY, BANKNIFTY, SENSEX
  - Calculates Greeks, Max Pain, PCR
  - Generates strategy recommendations

---

## ✅ Verification Checklist

- [ ] Port 5001 accessible: http://127.0.0.1:5001
- [ ] Dhan broker logged in (Broker Status shows "Connected")
- [ ] OpenAlgo API key generated/copied
- [ ] Option strategy updated to use port 5001 ✅
- [ ] Option strategy started and running

---

## 🐛 Troubleshooting

### Can't Login to Dhan

1. **Check Redirect URL**: Should be `http://127.0.0.1:5001/dhan/callback`
2. **Check Credentials**: Verify in Dhan dashboard
3. **Check Logs**: `tail -f log/app.log`

### Option Strategy Not Starting

1. **Check API Key**: Verify `OPENALGO_APIKEY` is set correctly
2. **Check API Host**: Should be `http://127.0.0.1:5001`
3. **Check Logs**: `tail -f log/strategies/advanced_options_ranker.log`
4. **Check Dhan Login**: Ensure broker is connected

### Strategy Can't Connect

1. **Verify Port**: `curl http://127.0.0.1:5001/api/v1/ping`
2. **Check API Key**: Must be valid OpenAlgo API key
3. **Check Environment**: Ensure `OPENALGO_HOST` and `OPENALGO_APIKEY` are set

---

## 📝 Next Steps After Login

1. **Monitor Strategy**: Check logs for option analysis
2. **Review Recommendations**: Strategy will generate option trade ideas
3. **Place Orders**: Via OpenAlgo API or Web UI

---

**Status**: ✅ Ready to login and start option strategies on port 5001!
