#!/usr/bin/env bash
# Quick verification script for self-hosted GitHub Actions runner
# Run this after setup to confirm everything is working

set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "🔍 Verifying self-hosted runner setup..."
echo ""

# Check 1: Runner directory exists
RUNNER_DIR="$HOME/actions-runner"
if [[ -d "$RUNNER_DIR" ]]; then
    echo -e "${GREEN}✓${NC} Runner directory exists: $RUNNER_DIR"
else
    echo -e "${RED}✗${NC} Runner directory not found. Run: make runner-setup"
    exit 1
fi

# Check 2: Runner service status
cd "$RUNNER_DIR" 2>/dev/null || exit 1
if ./svc.sh status &>/dev/null; then
    echo -e "${GREEN}✓${NC} Runner service is installed"
    STATUS=$(./svc.sh status 2>&1 | head -n1 || echo "unknown")
    if echo "$STATUS" | grep -q "running\|active"; then
        echo -e "${GREEN}✓${NC} Runner service is running"
    else
        echo -e "${YELLOW}⚠${NC} Runner service exists but may not be running"
        echo "   Run: cd ~/actions-runner && ./svc.sh start"
    fi
else
    echo -e "${YELLOW}⚠${NC} Runner service not installed"
    echo "   Run: cd ~/actions-runner && ./svc.sh install && ./svc.sh start"
fi

# Check 3: Docker
if command -v docker &> /dev/null; then
    if docker ps &>/dev/null; then
        echo -e "${GREEN}✓${NC} Docker is running"
    else
        echo -e "${YELLOW}⚠${NC} Docker installed but not running"
        echo "   Run: open -a Docker (or: colima start)"
    fi
else
    echo -e "${RED}✗${NC} Docker not found. Install via: brew install --cask docker"
fi

# Check 4: Required tools
for tool in jq curl; do
    if command -v "$tool" &> /dev/null; then
        echo -e "${GREEN}✓${NC} $tool installed"
    else
        echo -e "${RED}✗${NC} $tool not found. Install via: brew install $tool"
    fi
done

# Check 5: Port 8000 availability
if lsof -nP -iTCP:8000 -sTCP:LISTEN &>/dev/null; then
    PID=$(lsof -nP -iTCP:8000 -sTCP:LISTEN | awk 'NR==2 {print $2}')
    echo -e "${YELLOW}⚠${NC} Port 8000 is in use (PID: $PID)"
    echo "   Workflows may fail. Kill with: kill $PID"
    echo "   Or use: PORT=8010 in workflows"
else
    echo -e "${GREEN}✓${NC} Port 8000 is available"
fi

# Check 6: Runner logs (recent activity)
if [[ -d "$RUNNER_DIR/_diag" ]]; then
    LOG_COUNT=$(find "$RUNNER_DIR/_diag" -name "*.log" -type f 2>/dev/null | wc -l | tr -d ' ')
    if [[ "$LOG_COUNT" -gt 0 ]]; then
        echo -e "${GREEN}✓${NC} Runner logs found ($LOG_COUNT files)"
        echo "   View with: make runner-logs"
    else
        echo -e "${YELLOW}⚠${NC} No runner logs yet (normal if just installed)"
    fi
else
    echo -e "${YELLOW}⚠${NC} Runner logs directory not found"
fi

# Check 7: GitHub connectivity (if runner is configured)
if [[ -f "$RUNNER_DIR/.runner" ]]; then
    echo -e "${GREEN}✓${NC} Runner is configured"
    if curl -s --max-time 5 https://github.com &>/dev/null; then
        echo -e "${GREEN}✓${NC} GitHub is reachable"
    else
        echo -e "${YELLOW}⚠${NC} Cannot reach GitHub (check network)"
    fi
else
    echo -e "${YELLOW}⚠${NC} Runner not configured yet"
    echo "   Run: make runner-setup"
fi

echo ""
echo "📋 Next steps:"
echo "  1. Verify runner is online: GitHub → Settings → Actions → Runners"
echo "  2. Test workflow: GitHub → Actions → Run workflow"
echo "  3. Check status: make runner-status"
echo "  4. View logs: make runner-logs"
echo ""


