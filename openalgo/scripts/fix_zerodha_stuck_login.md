# Fix Zerodha Login Stuck Issue

## Problem
The Zerodha Kite Connect login page is stuck and not redirecting back to OpenAlgo.

## Solution Steps

### Option 1: Complete the Login Flow Properly

1. **First, ensure you're logged into OpenAlgo:**
   - Go to: `http://127.0.0.1:5001/auth/login`
   - Login with your OpenAlgo credentials
   - You should see the dashboard or broker selection page

2. **Then initiate broker connection:**
   - Go to: `http://127.0.0.1:5001/auth/broker`
   - Select "Zerodha" from the dropdown
   - Click "Connect Broker"
   - This will redirect you to Zerodha's login page

3. **Complete Zerodha login:**
   - Enter your Zerodha credentials
   - Enter TOTP/2FA if required
   - Click "Login" or "Authorize"
   - You should be redirected back to OpenAlgo automatically

### Option 2: If Already on Zerodha Login Page

If you're already on the Zerodha login page (the URL you provided):

1. **Complete the login:**
   - Enter your Zerodha user ID and password
   - Enter TOTP if prompted
   - Click "Login"

2. **After login:**
   - Zerodha should redirect you to: `http://127.0.0.1:5001/zerodha/callback?request_token=XXX&status=success`
   - If it doesn't redirect, check:
     - Is the OpenAlgo server running on port 5001?
     - Is the callback URL configured correctly in Zerodha Kite Connect app settings?

### Option 3: Check Callback URL Configuration

The callback URL must match exactly in:
1. **OpenAlgo .env file:** `REDIRECT_URL=http://127.0.0.1:5001/zerodha/callback`
2. **Zerodha Kite Connect App Settings:** 
   - Go to: https://kite.trade/apps/
   - Find your app (API Key: nhe2vo0afks02ojs)
   - Verify the "Redirect URL" matches: `http://127.0.0.1:5001/zerodha/callback`

### Option 4: Clear Session and Retry

If still stuck:

1. **Clear browser cookies for 127.0.0.1:5001**
2. **Restart the OpenAlgo server:**
   ```bash
   cd /Users/mac/dyad-apps/openalgo
   bash scripts/restart_server_clear_rate_limit.sh
   source venv/bin/activate
   FLASK_PORT=5001 python app.py
   ```
3. **Start fresh:**
   - Login to OpenAlgo
   - Go to broker connection page
   - Try connecting again

## Common Issues

- **Session expired:** Login to OpenAlgo first before connecting broker
- **Wrong callback URL:** Must match exactly in both places
- **Server not running:** Ensure OpenAlgo is running on port 5001
- **Browser blocking redirects:** Check browser console for errors

## Verification

After successful authentication, you should:
- See the OpenAlgo dashboard
- Be able to access market data
- Strategies should stop showing "No data in response" errors
