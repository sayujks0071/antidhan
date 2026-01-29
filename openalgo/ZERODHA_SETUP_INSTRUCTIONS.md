# Zerodha API Setup Instructions

## Issue: HTTP ERROR 400 from kite.zerodha.com

**Root Cause:** The `.env` file has placeholder values instead of your actual Zerodha API credentials.

## Solution: Configure Zerodha API Credentials

### Step 1: Get Your Zerodha API Credentials

1. **Log in to Zerodha Kite** (https://kite.zerodha.com)
2. **Go to Developer Console:**
   - Click on your profile → **API** → **My Apps**
   - Or visit: https://kite.trade/apps/
3. **Create a New App** (if you don't have one):
   - Click "Create new app"
   - Fill in:
     - **App name**: OpenAlgo (or any name)
     - **Redirect URL**: `http://127.0.0.1:5001/zerodha/callback`
     - **Product**: Select "Kite Connect"
   - Click "Create"
4. **Copy Your Credentials:**
   - **API Key**: (e.g., `abc123xyz456`)
   - **API Secret**: (e.g., `secret789key012`)

### Step 2: Update .env File

Edit `/Users/mac/dyad-apps/probable-fiesta/openalgo/.env` and replace:

```bash
BROKER_API_KEY = 'YOUR_BROKER_API_KEY'
BROKER_API_SECRET = 'YOUR_BROKER_API_SECRET'
```

With your actual credentials:

```bash
BROKER_API_KEY = 'your_actual_api_key_here'
BROKER_API_SECRET = 'your_actual_api_secret_here'
```

**Important:** 
- Keep the single quotes around the values
- Make sure `REDIRECT_URL = 'http://127.0.0.1:5001/zerodha/callback'` matches what you configured in Zerodha's developer console

### Step 3: Restart OpenAlgo Server

After updating `.env`, restart the server:

```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
lsof -ti:5001 | xargs kill
source venv/bin/activate
nohup python app.py > /tmp/openalgo_5001_fresh.log 2>&1 &
```

### Step 4: Try Connecting Again

1. Go to `http://127.0.0.1:5001/auth/broker`
2. Click on "Zerodha" 
3. You'll be redirected to Zerodha's login page
4. Log in and authorize the app
5. You'll be redirected back to OpenAlgo

## Troubleshooting

### If you still get HTTP 400:
1. **Verify API Key/Secret**: Double-check you copied them correctly (no extra spaces)
2. **Check Redirect URL**: Must match exactly in both `.env` and Zerodha developer console
3. **Check API Status**: Make sure your Zerodha API app is active in developer console
4. **Check Logs**: `tail -f /tmp/openalgo_5001_fresh.log` for detailed error messages

### Common Issues:
- **Redirect URL mismatch**: Must be exactly `http://127.0.0.1:5001/zerodha/callback`
- **API Key/Secret typos**: Check for extra spaces or missing characters
- **App not activated**: Make sure your app is active in Zerodha developer console
