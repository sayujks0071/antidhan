# Easy Go Installation (No Terminal Password Needed!)

## 🎯 Simplest Method: Download Go Installer

### Step 1: Download Go

1. Open your web browser
2. Go to: **https://go.dev/dl/**
3. Find the macOS section
4. Click the **big blue download button** for the latest version
   - For Apple Silicon (M1/M2/M3): Choose `goX.XX.X.darwin-arm64.pkg`
   - For Intel Mac: Choose `goX.XX.X.darwin-amd64.pkg`
5. The `.pkg` file will download to your Downloads folder

### Step 2: Install Go

1. Open **Finder**
2. Go to **Downloads** folder
3. Double-click the downloaded `.pkg` file (e.g., `go1.23.3.darwin-arm64.pkg`)
4. Follow the installer:
   - Click "Continue"
   - Click "Install"
   - Enter your Mac password in the GUI (this will show dots)
   - Wait for installation to complete
   - Click "Close"

**That's it!** No terminal password typing needed.

### Step 3: Verify Installation

Open Terminal and run:

```bash
go version
```

You should see something like: `go version go1.23.3 darwin/arm64`

## ✅ Next Steps

Once Go is installed:

```bash
cd /Users/mac/AITRAPP

# Setup MCP server
make mcp-setup

# Build MCP server
make mcp-build

# Run MCP server
make mcp-run-readonly
```

## 🔍 If Go Command Not Found

If `go version` doesn't work, you may need to:

1. **Close and reopen Terminal**
2. Or add Go to PATH manually:

```bash
# Add to ~/.zshrc
echo 'export PATH=$PATH:/usr/local/go/bin' >> ~/.zshrc
source ~/.zshrc
```

## 📝 Summary

**Easiest way**: Download `.pkg` file from https://go.dev/dl/ and double-click to install. No terminal password needed!

---

**This method uses the GUI installer - much easier than Homebrew!**

