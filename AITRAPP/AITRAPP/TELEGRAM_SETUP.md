# Telegram Bot Setup for CI Notifications

## Quick Setup

### 1. Bot Token (Already Provided)
```
8352104144:AAFUvdvr8tSPThMa7HghDsEtqr9wdrgQEsU
```

### 2. Get Your Chat ID

**Method 1: Via API**
```bash
# Replace YOUR_BOT_TOKEN with your token
curl -s "https://api.telegram.org/bot8352104144:AAFUvdvr8tSPThMa7HghDsEtqr9wdrgQEsU/getUpdates" | jq '.result[0].message.chat.id'
```

**Method 2: Via Bot**
1. Start a conversation with your bot on Telegram
2. Send any message to the bot
3. Visit: `https://api.telegram.org/bot8352104144:AAFUvdvr8tSPThMa7HghDsEtqr9wdrgQEsU/getUpdates`
4. Look for `"chat":{"id":123456789}` in the response
5. That number is your chat ID

### 3. Add to GitHub Secrets

Go to your repository:
- **Settings** → **Secrets and variables** → **Actions**
- Click **New repository secret**

Add these secrets:
- **Name**: `TG_BOT_TOKEN`
  - **Value**: `8352104144:AAFUvdvr8tSPThMa7HghDsEtqr9wdrgQEsU`

- **Name**: `TG_CHAT_ID`
  - **Value**: `<your_chat_id_from_step_2>`

### 4. Test the Bot

```bash
# Test bot is working
curl -s "https://api.telegram.org/bot8352104144:AAFUvdvr8tSPThMa7HghDsEtqr9wdrgQEsU/getMe" | jq

# Send a test message (replace CHAT_ID with your chat ID)
curl -s "https://api.telegram.org/bot8352104144:AAFUvdvr8tSPThMa7HghDsEtqr9wdrgQEsU/sendMessage" \
  -d chat_id="YOUR_CHAT_ID" \
  -d text="Test message from AITRAPP"
```

## How It Works

The CI workflow will automatically send a Telegram notification when:
- PAPER E2E test fails
- Pre-LIVE gate fails (if configured)

## Security Notes

⚠️ **IMPORTANT:**
- Never commit the bot token to git
- Store it only in GitHub Secrets
- Rotate the token if it's ever exposed
- The token shown here should be rotated after setup

## Troubleshooting

### "Bot token is invalid"
- Verify the token is correct
- Check for extra spaces or characters
- Ensure the bot hasn't been deleted

### "Chat not found"
- Make sure you've started a conversation with the bot
- Verify the chat_id is correct (it's a number, not a username)
- Try sending a message to the bot first

### Notifications not working
- Check GitHub Actions logs for errors
- Verify secrets are set correctly
- Test the bot manually using curl

