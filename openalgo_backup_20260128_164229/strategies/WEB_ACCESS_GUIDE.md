# OpenAlgo Web Interface Access Guide

## Current Status
✅ Server is running on port 5001
⚠️ You're getting 403 errors - likely due to rate limiting or authentication

## Step-by-Step Access Instructions

### Step 1: Access the Login Page

Open your browser and navigate to:
```
http://127.0.0.1:5001/auth/login
```

**NOT** `http://127.0.0.1:5000` (that's a different service)

### Step 2: If You See Rate Limit Error

If you see "Rate limit exceeded", wait 1-2 minutes and try again, or:

1. **Clear browser cookies** for `127.0.0.1:5001`
2. **Use a different browser** or **incognito/private mode**
3. **Wait a few minutes** before retrying

### Step 3: First Time Setup (If No User Exists)

If this is the first time accessing OpenAlgo:

1. Navigate to: `http://127.0.0.1:5001/setup`
2. Create an admin account:
   - Username: `sayujks0071` (or your preferred username)
   - Password: `Apollo@20417` (or your preferred password)
   - Email: (optional)
3. Click "Create Account"

### Step 4: Login

1. Go to: `http://127.0.0.1:5001/auth/login`
2. Enter your credentials:
   - Username: `sayujks0071`
   - Password: `Apollo@20417`
3. Click "Login"

### Step 5: Generate API Key

After logging in:

1. Navigate to: `http://127.0.0.1:5001/apikey`
   OR
   Go to: Settings → API Keys

2. Click **"Generate API Key"** button

3. **Copy the generated API key** (it will be a long hexadecimal string like `a1b2c3d4e5f6...`)

4. **Set it as environment variable:**
   ```bash
   export OPENALGO_APIKEY="your-generated-api-key-here"
   ```

### Step 6: Test API Key

```bash
cd openalgo/strategies
python3 scripts/test_api_key.py "your-generated-api-key"
```

You should see:
```
✅ API Key is VALID!
✅ Successfully retrieved X data points
```

### Step 7: Run Optimization

Once you have a valid API key:

```bash
cd openalgo/strategies
export OPENALGO_APIKEY="your-generated-api-key"
python3 scripts/optimize_strategies.py --strategies all --method hybrid
```

## Troubleshooting

### Still Getting 403 Error?

1. **Check if server is running:**
   ```bash
   lsof -i :5001 | grep LISTEN
   ```
   Should show Python process listening on port 5001

2. **Try accessing root URL:**
   ```
   http://127.0.0.1:5001/
   ```
   This should show the OpenAlgo homepage

3. **Check server logs:**
   Look at the terminal where the server is running for error messages

### Rate Limit Issues?

- Wait 5-10 minutes between attempts
- Clear browser cookies
- Use incognito/private browsing mode
- Try from a different browser

### Can't Access Setup Page?

If `/setup` doesn't work, the user might already exist. Try:
1. Go to `/auth/login` directly
2. Use your existing credentials
3. If you forgot password, use `/auth/reset-password`

## Quick Reference URLs

- **Homepage**: `http://127.0.0.1:5001/`
- **Login**: `http://127.0.0.1:5001/auth/login`
- **Setup** (first time): `http://127.0.0.1:5001/setup`
- **API Keys**: `http://127.0.0.1:5001/apikey`
- **Dashboard**: `http://127.0.0.1:5001/dashboard`
- **Strategies**: `http://127.0.0.1:5001/python`
- **Broker Auth**: `http://127.0.0.1:5001/auth/broker`

## Next Steps After Getting API Key

1. ✅ Test the API key with `test_api_key.py`
2. ✅ Run optimization: `python3 scripts/optimize_strategies.py --strategies all --method hybrid`
3. ✅ Review results in `optimization_results/` directory
4. ✅ Update strategies with best parameters
