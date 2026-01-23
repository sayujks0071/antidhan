# Installing Go - Manual Instructions

## Understanding Password Input

When you type your password in the terminal, **nothing appears on screen** - not even dots or asterisks. This is normal security behavior. Just type your password and press Enter.

## Step-by-Step Installation

### Step 1: Install Homebrew

Open Terminal and run:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

**What to expect:**
1. It will ask for your password
2. **Type your password** (you won't see anything - this is normal!)
3. Press Enter
4. Wait for installation to complete (may take 5-10 minutes)

**If you see "Need sudo access":**
- Make sure you're typing your **Mac user account password**
- The account must have Administrator privileges
- Try typing slowly and carefully

### Step 2: Add Homebrew to PATH

After Homebrew installs, it will show instructions. For Apple Silicon Macs (M1/M2/M3), run:

```bash
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zshrc
source ~/.zshrc
```

For Intel Macs, it's usually:
```bash
echo 'eval "$(/usr/local/bin/brew shellenv)"' >> ~/.zshrc
source ~/.zshrc
```

### Step 3: Verify Homebrew

```bash
brew --version
```

Should show something like: `Homebrew 4.x.x`

### Step 4: Install Go

```bash
brew install go
```

This will take a few minutes.

### Step 5: Verify Go

```bash
go version
```

Should show: `go version go1.xx.x darwin/amd64` or `darwin/arm64`

## Alternative: Direct Go Installation (No Homebrew)

If Homebrew is causing issues, you can install Go directly:

### Option A: Download Go Installer

1. Visit: https://go.dev/dl/
2. Download the macOS installer (`.pkg` file)
3. Double-click to install
4. Follow the GUI installer (no terminal password needed)

### Option B: Using Go Version Manager (g)

```bash
# Install g (Go version manager)
curl -sSL https://git.io/g-install | sh -s

# Install latest Go
g install latest
```

## Troubleshooting

### "Password not working"

- Make sure you're typing your **Mac login password**
- Check Caps Lock is off
- Try typing very slowly
- The password field is invisible - just type and press Enter

### "Command not found: brew"

After installing Homebrew, you may need to:
1. Close and reopen Terminal
2. Or run: `source ~/.zshrc`
3. Or run: `eval "$(/opt/homebrew/bin/brew shellenv)"` (Apple Silicon)
4. Or run: `eval "$(/usr/local/bin/brew shellenv)"` (Intel)

### "Permission denied"

- Make sure your user account is an Administrator
- Try: `sudo brew install go` (will ask for password again)

## Quick Check Commands

After installation, verify everything:

```bash
# Check Homebrew
brew --version

# Check Go
go version

# Check Go is in PATH
which go
```

## Next Steps After Installation

Once Go is installed:

```bash
cd /Users/mac/AITRAPP

# Setup MCP server
make mcp-setup

# Edit API keys (use your editor)
nano kite-mcp-server/.env
# Or: open -e kite-mcp-server/.env

# Build MCP server
make mcp-build

# Run in read-only mode
make mcp-run-readonly
```

## Still Having Issues?

If you're still unable to type the password:

1. **Try a different terminal**: Use iTerm2 or the built-in Terminal app
2. **Use GUI installer**: Download Go directly from https://go.dev/dl/
3. **Check keyboard**: Make sure keyboard is working in other apps
4. **Restart Terminal**: Close and reopen Terminal app

---

**Remember**: When typing passwords in terminal, nothing appears on screen. Just type your password and press Enter!

