# 🚀 Quick Login & Test Setup

## Current Status

✅ **Done:**
- `.env` file created with your API credentials
- PostgreSQL is running
- Redis is being set up

⚠️ **Need to do:**
1. Get Kite Access Token
2. Install Python 3.11+ (or use existing)
3. Install dependencies
4. Run database migrations
5. Start the app

---

## Step 1: Get Kite Access Token

You need to generate an access token from Kite Connect. Here are two ways:

### Option A: Using Kite Connect Login (Recommended)

1. Visit: https://kite.trade/connect/login?api_key=nhe2vo0afks02ojs&v=3
2. Login with your Zerodha credentials
3. You'll be redirected to: `http://localhost:8080/callback?request_token=XXXXX&action=login&status=success`
4. Copy the `request_token` from the URL
5. Run this command to generate access token:

```bash
cd /Users/mac/AITRAPP
python3 -c "
from kiteconnect import KiteConnect
import sys

api_key = 'nhe2vo0afks02ojs'
api_secret = 'cs82nkkdvin37nrydnyou6cwn2b8zojl'

# Replace YOUR_REQUEST_TOKEN with the token from URL
request_token = input('Paste request_token from URL: ')

kite = KiteConnect(api_key=api_key)
data = kite.generate_session(request_token, api_secret=api_secret)

print(f'\n✅ Access Token: {data[\"access_token\"]}')
print(f'✅ User ID: {data[\"user_id\"]}')
print(f'\nAdd these to your .env file:')
print(f'KITE_ACCESS_TOKEN={data[\"access_token\"]}')
print(f'KITE_USER_ID={data[\"user_id\"]}')
"
```

### Option B: Using MCP Server (If Already Authenticated)

If you've already authenticated with the MCP server, you might have the token stored. Check:

```bash
cat kite-mcp-server/.env | grep ACCESS_TOKEN
```

---

## Step 2: Update .env File

Edit `.env` and add your access token and user ID:

```bash
nano .env
# Or use your preferred editor
```

Update these lines:
```
KITE_ACCESS_TOKEN=your_actual_access_token_here
KITE_USER_ID=your_actual_user_id_here
```

---

## Step 3: Setup Python Environment

```bash
cd /Users/mac/AITRAPP

# Use Python 3.11 if available, otherwise install it
eval "$(/opt/homebrew/bin/brew shellenv)"
python3.11 -m venv venv  # or python3 if 3.11+ is default

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

---

## Step 4: Setup Database

```bash
# Make sure PostgreSQL is running
eval "$(/opt/homebrew/bin/brew shellenv)"
brew services start postgresql@16

# Create database if it doesn't exist
createdb aitrapp 2>/dev/null || echo "Database might already exist"

# Run migrations
alembic upgrade head
```

---

## Step 5: Start the App

```bash
# Make sure Redis is running
brew services start redis

# Start in PAPER mode (safe testing)
make paper

# Or start directly:
source venv/bin/activate
export APP_MODE=PAPER
python -m uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Step 6: Test the App

In a new terminal:

```bash
# Check health
curl http://localhost:8000/health | jq

# Check system state
curl http://localhost:8000/state | jq

# View positions (should be empty)
curl http://localhost:8000/positions | jq

# View metrics
curl http://localhost:8000/metrics
```

---

## Troubleshooting

### Python Version Issue
If you get errors about Python version:
```bash
# Install Python 3.11
brew install python@3.11

# Use it explicitly
/opt/homebrew/opt/python@3.11/bin/python3.11 -m venv venv
```

### Database Connection Error
```bash
# Check PostgreSQL is running
brew services list | grep postgresql

# Check connection
psql -h localhost -U trader -d aitrapp
```

### Redis Connection Error
```bash
# Start Redis
brew services start redis

# Test connection
redis-cli ping
```

---

## Next Steps

Once the app is running:
1. Monitor logs: `tail -f logs/aitrapp.log | jq`
2. Check dashboard: Open http://localhost:3000 (if web app is running)
3. Test strategies in PAPER mode
4. Review `LAUNCH_CARD.md` before going LIVE

---

**Need help?** Check:
- `FAST_FAQ.md` - Quick diagnostics
- `QUICKSTART.md` - Detailed setup guide
- `README.md` - Full documentation

