# Kite MCP Server - Quick Start

## ✅ Repository Cloned

The Kite MCP Server has been cloned to: `kite-mcp-server/`

## 🚀 Quick Setup

### Option 1: Use Hosted Version (Easiest)

No installation needed! Use Zerodha's hosted server:

```
https://mcp.kite.trade/mcp
```

**For Claude Desktop**, add to `~/.config/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "kite": {
      "command": "npx",
      "args": ["mcp-remote", "https://mcp.kite.trade/mcp"]
    }
  }
}
```

### Option 2: Self-Host (More Control)

```bash
# 1. Setup environment
make mcp-setup

# 2. Edit API keys
nano kite-mcp-server/.env

# 3. Build and run
make mcp-run

# Or run in read-only mode (safer)
make mcp-run-readonly
```

## 📋 Available Commands

```bash
make mcp-build          # Build MCP server (requires Go)
make mcp-setup          # Create .env file
make mcp-run            # Run MCP server
make mcp-run-readonly   # Run in read-only mode (no trading)
make mcp-status         # Check if server is running
```

## 🎯 What It Does

The MCP server provides AI assistants (like Claude) with access to:

- ✅ Market data (quotes, OHLC, historical)
- ✅ Portfolio information (holdings, positions, margins)
- ✅ Order management (place, modify, cancel)
- ✅ Instrument search
- ✅ GTT orders

## 🔗 Integration with AITRAPP

Run both services in parallel:

```bash
# Terminal 1: AITRAPP
make paper

# Terminal 2: MCP Server (read-only)
make mcp-run-readonly
```

Now you can:
- Use AITRAPP for automated trading
- Use AI assistant for analysis and suggestions
- Get AI insights on your portfolio

## 📚 Full Documentation

See `docs/KITE_MCP_INTEGRATION.md` for complete guide.

## ⚠️ Security Note

For safety, start with read-only mode:

```bash
make mcp-run-readonly
```

This excludes trading tools, allowing only data queries.

---

**Ready to use!** The MCP server adds AI capabilities to your trading workflow.

