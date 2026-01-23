# Setup Guide

## 🔧 Quick Setup (Recommended)

### 1. Set up clean virtual environment
```bash
make setup-venv
```

This will:
- Create a new virtual environment
- Upgrade pip, setuptools, wheel
- Install all pinned dependencies
- Run sanity check

### 2. Activate virtual environment
```bash
source venv/bin/activate
```

### 3. Start PAPER session
```bash
make start-paper
```

## 📦 Manual Setup

### Step 1: Create virtual environment
```bash
python3 -m venv venv
source venv/bin/activate
```

### Step 2: Upgrade base packages
```bash
python -m pip install -U pip setuptools wheel
```

### Step 3: Install dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Quick sanity check
```bash
python -c "import fastapi, uvicorn; print('✅ deps_ok')"
```

## 🚀 Start PAPER Session

### Option 1: Automated (Recommended)
```bash
make start-paper
```

### Option 2: Manual
```bash
# Activate venv first
source venv/bin/activate

# Start PAPER
PORT=8000 make paper
```

## ✅ Verify Setup

### Check dependencies
```bash
python -c "import fastapi, uvicorn, sqlalchemy, redis, prometheus_client; print('✅ All core deps OK')"
```

### Check API starts
```bash
make start-paper
# Wait for "API is responding" message
```

### Run prove-out
```bash
make quick-proveout
```

## 🐛 Troubleshooting

### psycopg2 build issues (Linux/ARM)
The `requirements.txt` already uses `psycopg2-binary` which should work. If you still have issues:

```bash
# Try installing system dependencies first
# Ubuntu/Debian:
sudo apt-get install libpq-dev python3-dev

# macOS:
brew install postgresql

# Then reinstall
pip install --force-reinstall psycopg2-binary
```

### Use Docker instead
```bash
docker compose up api
```

### Virtual environment not activating
```bash
# Check Python version
python3 --version  # Should be 3.11+

# Recreate venv
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Dependencies conflict
```bash
# Clean install
rm -rf venv
make setup-venv
```

## 📋 Pinned Dependencies

All dependencies are pinned to specific version ranges for stability:

- **fastapi**: 0.115.x
- **uvicorn**: 0.30.x - 0.31.x
- **SQLAlchemy**: 2.0.x
- **alembic**: 1.13.x
- **psycopg2-binary**: 2.9.x
- **redis**: 5.x
- **prometheus-client**: 0.20.x - 0.21.x
- **kiteconnect**: 5.x
- **pandas**: 2.2.x
- **pydantic**: 2.9.x - 2.10.x

## 💡 Pro Tips

1. **Auto-activate venv**: Add to your `~/.zshrc` or `~/.bashrc`:
   ```bash
   cd() {
     builtin cd "$@"
     if [ -f "venv/bin/activate" ]; then
       source venv/bin/activate
     fi
   }
   ```

2. **Check if venv is active**:
   ```bash
   which python  # Should show venv/bin/python
   ```

3. **Update dependencies**:
   ```bash
   pip install --upgrade -r requirements.txt
   ```

4. **Freeze current versions** (if you want exact pins):
   ```bash
   pip freeze > requirements-frozen.txt
   ```

## 🎯 Next Steps

After setup:
1. ✅ Run `make setup-venv` (if not done)
2. ✅ Activate venv: `source venv/bin/activate`
3. ✅ Start PAPER: `make start-paper`
4. ✅ Open dashboard: `make live-dashboard && tmux attach -t live`
5. ✅ Run prove-out: `make quick-proveout`

