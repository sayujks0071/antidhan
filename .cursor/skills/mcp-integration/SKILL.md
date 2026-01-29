# MCP Integration Skill

This skill manages and integrates multiple MCP servers (Kite and OpenAlgo) for seamless trading operations.

## Purpose

- Configure and manage MCP servers
- Troubleshoot MCP connection issues
- Ensure both servers are accessible
- Coordinate operations across MCP servers

## MCP Servers Managed

### 1. Kite MCP
- **Type**: Hosted server
- **URL**: `https://mcp.kite.trade/mcp`
- **Command**: `npx mcp-remote https://mcp.kite.trade/mcp`
- **Requirements**: Node.js, internet connection

### 2. OpenAlgo MCP
- **Type**: Local server
- **Port**: 5002 (Dhan) or 5001 (Kite)
- **Command**: Python script with API key
- **Requirements**: OpenAlgo server running, valid API key

## Configuration Management

### Configuration File

**Primary**: `~/.cursor/mcp.json`

**Structure**:
```json
{
  "mcpServers": {
    "kite": {
      "command": "npx",
      "args": ["mcp-remote", "https://mcp.kite.trade/mcp"]
    },
    "openalgo": {
      "command": "/opt/homebrew/bin/python3",
      "args": [
        "/path/to/mcpserver.py",
        "API_KEY",
        "http://127.0.0.1:5002"
      ]
    }
  }
}
```

### Verification Steps

1. **Check Configuration**:
   ```bash
   cat ~/.cursor/mcp.json | python3 -m json.tool
   ```

2. **Verify Servers**:
   - Kite: No local server needed
   - OpenAlgo: Check if server is running

3. **Test Connectivity**:
   - Kite: Ask Cursor "What Kite MCP tools are available?"
   - OpenAlgo: Ask Cursor "What OpenAlgo MCP tools are available?"

## Common Operations

### Restore Missing MCP Server

If a server disappears from configuration:

```python
import json
import os

mcp_file = os.path.expanduser("~/.cursor/mcp.json")

# Read existing config
with open(mcp_file, 'r') as f:
    config = json.load(f)

# Add missing server
if "openalgo" not in config.get("mcpServers", {}):
    config["mcpServers"]["openalgo"] = {
        "command": "/opt/homebrew/bin/python3",
        "args": [
            "/Users/mac/dyad-apps/probable-fiesta/openalgo/mcp/mcpserver.py",
            "API_KEY",
            "http://127.0.0.1:5002"
        ]
    }

# Save
with open(mcp_file, 'w') as f:
    json.dump(config, f, indent=2)
```

### Update API Key

```python
# Update OpenAlgo MCP API key
config["mcpServers"]["openalgo"]["args"][1] = "NEW_API_KEY"
```

### Change Port

```python
# Switch OpenAlgo MCP to port 5001
config["mcpServers"]["openalgo"]["args"][2] = "http://127.0.0.1:5001"
```

## Troubleshooting

### Issue: MCP Server Not Appearing

**Diagnosis**:
1. Check `~/.cursor/mcp.json` exists and is valid JSON
2. Verify server is in `mcpServers` object
3. Check Cursor was restarted after config change

**Fix**:
1. Restore configuration
2. Restart Cursor IDE
3. Verify in Settings → MCP

### Issue: OpenAlgo MCP Connection Failed

**Diagnosis**:
1. Check OpenAlgo server is running: `lsof -i :5002`
2. Verify API key is correct
3. Check port matches configuration

**Fix**:
1. Start OpenAlgo server
2. Update API key if needed
3. Restart Cursor

### Issue: Kite MCP Not Working

**Diagnosis**:
1. Check internet connection
2. Verify npx is available: `npx --version`
3. Check hosted server accessibility

**Fix**:
1. Ensure Node.js is installed
2. Check network connectivity
3. Try accessing hosted server directly

## Best Practices

1. **Always backup** configuration before changes
2. **Restart Cursor** after configuration updates
3. **Verify both servers** are configured
4. **Test connectivity** after changes
5. **Keep API keys secure** (don't commit to git)

## Related Files

- Configuration: `~/.cursor/mcp.json`
- Backup: `~/.cursor/mcp.json.backup.*`
- OpenAlgo MCP: `/Users/mac/dyad-apps/probable-fiesta/openalgo/mcp/mcpserver.py`

---

**Use this skill** to manage and integrate MCP servers for seamless trading operations.
