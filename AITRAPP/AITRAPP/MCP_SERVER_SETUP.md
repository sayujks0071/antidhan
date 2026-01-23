# MCP Server Setup - Complete Guide

## ✅ Current Status

- ✅ Homebrew installed
- ✅ Go installed (v1.25.4)
- ✅ MCP server built
- ✅ API keys configured
- ✅ Callback endpoint ready: `http://localhost:8080/callback`

## 🔧 Important: Register Redirect URL

**Before starting the server**, you need to register the callback URL in your Kite Connect app:

1. Go to: https://developers.kite.trade/apps/
2. Select your app (or create one)
3. Add redirect URL: `http://localhost:8080/callback`
4. Save the settings

**This is required for OAuth authentication to work!**

## 🚀 Starting the MCP Server

### Option 1: Read-Only Mode (Recommended for First Time)

```bash
cd /Users/mac/AITRAPP
make mcp-run-readonly
```

This starts the server with trading tools disabled (safer).

### Option 2: Full Access Mode

```bash
cd /Users/mac/AITRAPP
make mcp-run
```

This gives full access including trading tools.

## 📍 Server Endpoints

Once running, the server will be available at:

- **Status Page**: http://localhost:8080/
- **MCP Endpoint**: http://localhost:8080/mcp
- **SSE Endpoint**: http://localhost:8080/sse
- **Callback**: http://localhost:8080/callback

## 🔐 Authentication Flow

1. **Start MCP server**
2. **Use the `login` tool** (via MCP client)
3. **Get authorization URL** from the server
4. **Open URL in browser** and login to Kite
5. **Kite redirects** to `http://localhost:8080/callback`
6. **Server completes authentication**
7. **Session is established**

## 🧪 Testing the Server

### Check if Running

```bash
make mcp-status
```

Or open: http://localhost:8080/

### Test Callback Endpoint

```bash
curl http://localhost:8080/callback
```

Should return an error (expected - needs proper OAuth params).

## 📋 Quick Commands

```bash
# Start server (read-only)
make mcp-run-readonly

# Start server (full access)
make mcp-run

# Check status
make mcp-status

# Rebuild if needed
make mcp-build
```

## 🔗 Integration with Claude Desktop

Once the server is running, configure Claude Desktop:

Edit `~/.config/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "kite": {
      "command": "npx",
      "args": ["mcp-remote", "http://localhost:8080/mcp", "--allow-http"],
      "env": {
        "KITE_API_KEY": "nhe2vo0afks02ojs",
        "KITE_API_SECRET": "cs82nkkdvin37nrydnyou6cwn2b8zojl"
      }
    }
  }
}
```

**Note**: You can also use environment variables instead of hardcoding keys.

## ⚠️ Security Notes

1. **Register Redirect URL**: Must match exactly in Kite Connect app settings
2. **Localhost Only**: Server runs on localhost for security
3. **Read-Only First**: Start with read-only mode to test safely
4. **API Keys**: Keep them secure, don't commit to git

## 🐛 Troubleshooting

### "Invalid redirect URI"

- Make sure `http://localhost:8080/callback` is registered in Kite Connect app
- Check the URL matches exactly (no trailing slash)

### "Server won't start"

- Check if port 8080 is available: `lsof -i :8080`
- Kill process if needed: `kill -9 <PID>`

### "Authentication fails"

- Verify API keys in `.env` file
- Check redirect URL is registered
- Make sure server is running when you try to login

## 📚 Next Steps

1. ✅ Register redirect URL in Kite Connect
2. ✅ Start server: `make mcp-run-readonly`
3. ✅ Test status page: http://localhost:8080/
4. ✅ Configure Claude Desktop (if using)
5. ✅ Test authentication flow

---

**Ready to start!** Run `make mcp-run-readonly` after registering the redirect URL.

