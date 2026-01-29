# How to View MCP Servers in Cursor IDE

## ✅ Configuration Status

Your OpenAlgo MCP server is configured in **3 locations**:

1. ✅ `~/Library/Application Support/Cursor/User/settings.json`
2. ✅ `~/.cursor/mcp.json` (Primary MCP config file)
3. ✅ `~/.cursor/config/mcp.json`

## 🔍 How to View MCP Servers in Cursor

### Method 1: Settings UI (Recommended)

1. **Open Cursor Settings**:
   - Press `Cmd + ,` (macOS) or `Ctrl + ,` (Windows/Linux)
   - Or: **Cursor → Settings** from menu

2. **Search for MCP**:
   - In the settings search bar, type: `MCP`
   - Look for sections like:
     - **"MCP Servers"**
     - **"Model Context Protocol"**
     - **"Features → MCP"**

3. **Check MCP Status**:
   - You should see a list of configured MCP servers
   - Look for `openalgo` in the list
   - There may be toggle switches to enable/disable servers

### Method 2: Command Palette

1. **Open Command Palette**:
   - Press `Cmd + Shift + P` (macOS) or `Ctrl + Shift + P` (Windows/Linux)

2. **Search for MCP**:
   - Type: `MCP`
   - Look for commands like:
     - `MCP: Show Servers`
     - `MCP: Restart Server`
     - `MCP: Configure Servers`

### Method 3: Check MCP Logs

1. **Open Output Panel**:
   - Press `Cmd + Shift + U` (macOS) or `Ctrl + Shift + U` (Windows/Linux)
   - Or: **View → Output** from menu

2. **Select MCP Logs**:
   - In the dropdown, select: **"MCP"** or **"anysphere.cursor-mcp"**
   - Check for any errors or connection status

### Method 4: Verify Configuration Files

Check the configuration files directly:

```bash
# Check primary MCP config
cat ~/.cursor/mcp.json | python3 -m json.tool

# Check Cursor settings
cat ~/Library/Application\ Support/Cursor/User/settings.json | grep -A 10 "mcpServers"
```

## 🔧 Troubleshooting

### Issue: MCP servers not showing in Settings

**Possible Causes**:
1. **Cursor version too old** - MCP support requires Cursor 0.40+ or later
2. **MCP feature disabled** - Check if MCP is enabled in experimental features
3. **Settings UI location** - MCP might be under "Features" or "Experimental"

**Solutions**:

1. **Update Cursor**:
   ```bash
   # Check version
   cursor --version
   # Update if needed: Cursor → Check for Updates
   ```

2. **Enable Experimental Features**:
   - Settings → Features → Experimental
   - Enable "MCP Support" or "Model Context Protocol"

3. **Check Settings Location**:
   - Settings → Features → MCP
   - Or: Settings → Extensions → MCP

### Issue: MCP server not connecting

**Check MCP Logs**:
```bash
# View recent MCP logs
tail -50 ~/Library/Application\ Support/Cursor/logs/*/window*/exthost/anysphere.cursor-mcp/*.log
```

**Verify Server Works**:
```bash
# Test MCP server directly
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
python3 mcp/mcpserver.py YOUR_API_KEY http://127.0.0.1:5001
```

### Issue: "openalgo" server not in list

**Verify Configuration**:
```bash
# Check if openalgo is in mcp.json
cat ~/.cursor/mcp.json | grep -i "openalgo"

# If not found, re-run setup
cd /Users/mac/dyad-apps/probable-fiesta/openalgo/mcp
./fix_cursor_mcp.sh
```

## 📋 Current Configuration

Your OpenAlgo MCP server is configured as:

```json
{
  "mcpServers": {
    "openalgo": {
      "command": "/opt/homebrew/bin/python3",
      "args": [
        "/Users/mac/dyad-apps/probable-fiesta/openalgo/mcp/mcpserver.py",
        "630db05e091812b4c23298ca2d018b62376ddd168860d21fcb4bd2dfc265e49f",
        "http://127.0.0.1:5001"
      ]
    }
  }
}
```

## ✅ Verification Steps

1. **Restart Cursor** completely (Cmd + Q, then reopen)
2. **Open Settings** (Cmd + ,)
3. **Search for "MCP"**
4. **Look for "openalgo"** in the server list
5. **Test in chat**: Ask "What OpenAlgo tools are available?"

## 💡 Alternative: Use MCP via Chat

Even if you don't see it in Settings, try using it directly:

1. **Open a new chat** in Cursor
2. **Ask**: "What MCP tools are available?"
3. **Or**: "Use OpenAlgo to get my account funds"

If MCP is working, Cursor will automatically use the tools!

---

**Need more help?** Check the MCP logs or verify the configuration files above.
