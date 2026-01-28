# OpenAlgo API Key Setup Guide

## Current Status
❌ The provided API key (`nhe2vo0afks02ojs`) is **INVALID** and needs to be regenerated.

## How to Generate a Valid API Key

### Step 1: Access OpenAlgo Web Interface
1. Open your browser and navigate to:
   ```
   http://127.0.0.1:5000
   ```
   (or your OpenAlgo server URL)

### Step 2: Login
- **Username**: `sayujks0071`
- **Password**: `Apollo@20417`

### Step 3: Generate API Key
1. After logging in, navigate to:
   - **Settings → API Keys**, OR
   - Direct URL: `http://127.0.0.1:5000/apikey`

2. Click **"Generate API Key"** button

3. **Copy the generated API key** (it will be a long hexadecimal string)

### Step 4: Set Environment Variable
```bash
export OPENALGO_APIKEY="your-generated-api-key-here"
```

### Step 5: Verify API Key
```bash
cd openalgo/strategies
python3 scripts/test_api_key.py "your-generated-api-key-here"
```

If successful, you should see:
```
✅ API Key is VALID!
✅ Successfully retrieved X data points
```

## Running Optimization

Once you have a valid API key:

```bash
cd openalgo/strategies
export OPENALGO_APIKEY="your-valid-api-key"
python3 scripts/optimize_strategies.py --strategies all --method hybrid
```

## Troubleshooting

### API Key Still Invalid?
1. Make sure you're logged in to OpenAlgo web interface
2. Check that the API key was copied completely (no spaces, full length)
3. Try regenerating the API key
4. Verify the OpenAlgo server is running: `curl http://127.0.0.1:5001/api/v1/ping`

### 403 Forbidden Error?
- API key is invalid or expired
- User account may not have API access enabled
- Try regenerating the API key

### Server Not Responding?
- Check if OpenAlgo server is running
- Verify the host URL (default: `http://127.0.0.1:5001`)
- Check server logs for errors
