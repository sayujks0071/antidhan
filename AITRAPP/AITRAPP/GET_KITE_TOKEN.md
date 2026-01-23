# How to Get Kite Access Token

## Quick Method (Using Helper Script)

You already have a helper script! Run:

```bash
cd /Users/mac/AITRAPP
source venv/bin/activate
python get_kite_token.py YOUR_REQUEST_TOKEN
```

But first, you need to get the `request_token` from Kite Connect.

## Step-by-Step Process

### Step 1: Visit Kite Connect Login URL

Open this URL in your browser:

```
https://kite.trade/connect/login?api_key=nhe2vo0afks02ojs&v=3
```

**Or use this direct link:**
- Replace `nhe2vo0afks02ojs` with your API key if different
- The URL format is: `https://kite.trade/connect/login?api_key=YOUR_API_KEY&v=3`

### Step 2: Login with Zerodha Credentials

- Enter your Zerodha Kite username and password
- Complete 2FA if prompted
- You'll be redirected to a callback URL

### Step 3: Get Request Token from Redirect URL

After login, you'll be redirected to a URL like:

```
http://localhost:8080/callback?request_token=XXXXX&action=login&status=success
```

**Copy the `request_token` value** (the part after `request_token=`)

**Note:** The "connection refused" error is normal - you just need the token from the URL!

### Step 4: Generate Access Token

Run the helper script with your request token:

```bash
cd /Users/mac/AITRAPP
source venv/bin/activate
python get_kite_token.py YOUR_REQUEST_TOKEN_HERE
```

The script will:
- Generate your access token and user ID
- Automatically update your `.env` file
- Show you the credentials

### Step 5: Update GitHub Secrets (for CI)

If you're using CI/CD, also add to GitHub Secrets:
- Go to: Settings → Secrets and variables → Actions
- Add: `KITE_ACCESS_TOKEN` = `<your_access_token>`
- Add: `KITE_USER_ID` = `<your_user_id>`

## Manual Method (Without Script)

If you prefer to do it manually:

```python
from kiteconnect import KiteConnect

api_key = "nhe2vo0afks02ojs"
api_secret = "cs82nkkdvin37nrydnyou6cwn2b8zojl"
request_token = "YOUR_REQUEST_TOKEN_FROM_URL"

kite = KiteConnect(api_key=api_key)
data = kite.generate_session(request_token, api_secret=api_secret)

print(f"Access Token: {data['access_token']}")
print(f"User ID: {data['user_id']}")
```

## Important Notes

### Token Expiry
- **Access tokens expire daily** (usually at midnight IST)
- You'll need to regenerate the token each day
- The request token expires quickly (within minutes), so use it immediately

### Token Refresh
Your code has automatic token refresh guards, but:
- For **local development**: Update `.env` file daily
- For **CI/CD**: Update GitHub secret `KITE_ACCESS_TOKEN` daily

### Security
- Never commit access tokens to git
- Store in `.env` file (already in `.gitignore`)
- Use GitHub Secrets for CI/CD

## Troubleshooting

### "Token is invalid or has expired"
- Request tokens expire quickly - use it within a few minutes
- Generate a fresh request token by logging in again

### "Connection refused" on callback
- This is normal! You just need the `request_token` from the URL
- The callback URL doesn't need to work - it's just for getting the token

### "Invalid API key"
- Verify your API key is correct: `nhe2vo0afks02ojs`
- Check that the API key is active in Kite Connect dashboard

### Token not working in CI
- Ensure GitHub secret `KITE_ACCESS_TOKEN` is updated
- Tokens expire daily - update the secret each morning
- Check the secret name matches exactly (case-sensitive)

## Quick Reference

**Login URL:**
```
https://kite.trade/connect/login?api_key=nhe2vo0afks02ojs&v=3
```

**Your API Credentials:**
- API Key: `nhe2vo0afks02ojs`
- API Secret: `cs82nkkdvin37nrydnyou6cwn2b8zojl`

**Helper Script:**
```bash
python get_kite_token.py REQUEST_TOKEN
```

## Daily Routine

Since tokens expire daily, your morning routine should include:

1. **Before market open:**
   - Visit login URL and get new request token
   - Run `python get_kite_token.py REQUEST_TOKEN`
   - Update GitHub secret if using CI

2. **Or automate it:**
   - Consider creating a script to auto-refresh tokens
   - Use Kite Connect's refresh token API (if available)

