# Secrets Hygiene Guide

Best practices for managing secrets in GitHub Actions and local development.

## GitHub Actions Secrets

Set these as **Actions secrets** (not variables) in your repository:

### Required Secrets

1. **`KITE_API_KEY`** - Your Zerodha Kite Connect API key
2. **`KITE_API_SECRET`** - Your Zerodha Kite Connect API secret
3. **`KITE_ACCESS_TOKEN`** - Kite Connect access token (rotates daily)
4. **`KITE_USER_ID`** - Your Kite Connect user ID

### Optional Secrets (for notifications)

5. **`TG_BOT_TOKEN`** - Telegram bot token (for failure alerts)
6. **`TG_CHAT_ID`** - Telegram chat ID (for failure alerts)

## How to Set Secrets

1. Go to your GitHub repository
2. Navigate to **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add each secret with its value
5. Click **Add secret**

## Token Rotation

### Daily Rotation

`KITE_ACCESS_TOKEN` expires daily. You need to:

1. **Generate new token** (via Kite Connect login)
2. **Update GitHub secret** with new token
3. **Update local `.env`** file

### Automated Rotation (Future)

Consider automating token refresh:
- Use Kite Connect's token refresh API
- Store refresh token securely
- Auto-update GitHub secrets via GitHub API

## Local Development

For local development, use `.env` file (never commit this):

```bash
# .env (in .gitignore)
KITE_API_KEY=your_key_here
KITE_API_SECRET=your_secret_here
KITE_ACCESS_TOKEN=your_token_here
KITE_USER_ID=your_user_id_here
```

## Security Best Practices

1. ✅ **Never commit secrets** to git
2. ✅ **Use GitHub Actions secrets** (not variables) for sensitive data
3. ✅ **Rotate tokens regularly** (especially access tokens)
4. ✅ **Use least privilege** - only grant necessary permissions
5. ✅ **Monitor secret usage** - check GitHub audit logs
6. ✅ **Use separate tokens** for CI/CD and local development if possible

## Token Refresh Guards

Your code already has token refresh guards:
- `packages/core/kite_client.py` - Handles token expiry
- `packages/core/orchestrator.py` - Retry logic for auth errors

But CI needs a **valid token at runtime** - ensure it's updated before the scheduled run.

## Verification

Test that secrets are set correctly:

```bash
# In GitHub Actions, secrets are available as environment variables
echo "Token set: $([ -n "$KITE_ACCESS_TOKEN" ] && echo 'yes' || echo 'no')"
```

## Troubleshooting

### "Token expired" errors in CI

1. Check if `KITE_ACCESS_TOKEN` secret is up to date
2. Generate new token via Kite Connect
3. Update GitHub secret
4. Re-run the workflow

### "Secret not found" errors

1. Verify secret name matches exactly (case-sensitive)
2. Check repository settings → Secrets
3. Ensure you're using `${{ secrets.SECRET_NAME }}` syntax

