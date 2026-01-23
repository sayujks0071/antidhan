#!/bin/bash
# LIVE switch ops script - spins up tmux dashboard and manages LIVE mode

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if tmux is installed
if ! command -v tmux &> /dev/null; then
    log_error "tmux is not installed. Install with: brew install tmux"
    exit 1
fi

# Check if jq is installed
if ! command -v jq &> /dev/null; then
    log_error "jq is not installed. Install with: brew install jq"
    exit 1
fi

# Check if API is running
if ! curl -s localhost:8000/health > /dev/null 2>&1; then
    log_error "API is not running. Start with: make paper"
    exit 1
fi

# Create incident snapshot directory
INCIDENT_DIR="$PROJECT_ROOT/reports/incidents"
mkdir -p "$INCIDENT_DIR"

# Function to create tmux dashboard
create_dashboard() {
    log_info "Creating tmux dashboard..."
    
    # Kill existing session if it exists
    tmux kill-session -t live 2>/dev/null || true
    
    # Create new session
    tmux new-session -d -s live
    tmux rename-window -t live:0 LIVE
    
    # Pane 0: Key metrics (top-left)
    tmux send-keys -t live:0 'watch -n5 "curl -s localhost:8000/metrics | grep -E \"^trader_(is_leader|order_latency_ms|portfolio_heat_rupees|marketdata_heartbeat_seconds|order_stream_heartbeat_seconds|kill_switch_total)\""' C-m
    
    # Pane 1: Positions/Heat/P&L (top-right)
    tmux split-window -h -t live:0
    tmux send-keys -t live:0.1 'watch -n2 "curl -s localhost:8000/state 2>/dev/null | jq -r \"\\\"Positions: \\(.positions | length)\\nHeat: ₹\\(.risk.portfolio_heat_rupees // 0)\\nP&L: ₹\\(.risk.daily_pnl_rupees // 0)\\\"\" || echo \"Waiting for API...\""' C-m
    
    # Pane 2: Redis event feed (bottom-right)
    tmux split-window -v -t live:0.1
    tmux send-keys -t live:0.2 'redis-cli --raw SUBSCRIBE orders events risk 2>/dev/null || echo "Redis not available"' C-m
    
    # Pane 3: Audit log tail (bottom-left)
    tmux select-pane -t live:0.0
    tmux split-window -v -t live:0.0
    tmux send-keys -t live:0.3 'tail -F logs/aitrapp.log 2>/dev/null | jq -r ".[\"level\",\"category\",\"message\"]|@tsv" 2>/dev/null || tail -F logs/aitrapp.log' C-m
    
    # Pane 4: Risk caps (bottom-center)
    tmux select-pane -t live:0.2
    tmux split-window -v -t live:0.2
    tmux send-keys -t live:0.4 'watch -n5 "curl -s localhost:8000/risk 2>/dev/null | jq -r \"\\\"Per-trade: \\(.per_trade_risk_pct)%\\nHeat cap: \\(.max_portfolio_heat_pct)%\\nDaily loss: \\(.daily_loss_stop_pct)%\\\"\" || echo \"Waiting for API...\""' C-m
    
    # Select pane 0
    tmux select-pane -t live:0.0
    
    log_info "Dashboard created. Attach with: tmux attach -t live"
}

# Function to run canary pre-check
canary_precheck() {
    log_info "Running canary pre-check..."
    
    echo ""
    echo "1. Checking leader lock and heartbeats..."
    curl -s localhost:8000/metrics | grep -E '^trader_is_leader|trader_.*heartbeat' | sort || log_warn "Some metrics missing"
    
    echo ""
    echo "2. Testing flatten (must be ≤2s)..."
    START=$(date +%s)
    curl -s -X POST localhost:8000/flatten -H "Content-Type: application/json" -d '{"reason":"prelive_sanity"}' | jq || log_error "Flatten failed"
    END=$(date +%s)
    DURATION=$((END - START))
    echo "   Duration: ${DURATION}s"
    if [ $DURATION -le 2 ]; then
        log_info "✅ Flatten ≤2s"
    else
        log_warn "⚠️  Flatten >2s (${DURATION}s)"
    fi
    
    echo ""
    echo "3. Checking positions (must be 0)..."
    POS_COUNT=$(curl -s localhost:8000/positions 2>/dev/null | jq '.count // 0' || echo "0")
    if [ "$POS_COUNT" = "0" ]; then
        log_info "✅ Zero positions"
    else
        log_warn "⚠️  Found $POS_COUNT positions"
    fi
    
    echo ""
    log_info "Pre-check complete"
}

# Function to switch to LIVE
switch_to_live() {
    log_info "Switching to LIVE mode..."
    
    RESPONSE=$(curl -s -X POST localhost:8000/mode \
        -H "Content-Type: application/json" \
        -d '{"mode":"LIVE","confirm":"CONFIRM LIVE TRADING"}')
    
    echo "$RESPONSE" | jq
    
    if echo "$RESPONSE" | jq -e '.status == "LIVE"' > /dev/null; then
        log_info "✅ Switched to LIVE mode"
        
        # Create incident snapshot on LIVE switch
        TIMESTAMP=$(date +%Y%m%d_%H%M%S)
        python3 -c "
from packages.core.incident_snapshot import snapshot_incident
snapshot_incident('LIVE_SWITCH', {'timestamp': '$(date -u +%Y-%m-%dT%H:%M:%SZ)', 'mode': 'LIVE'})
" 2>/dev/null || log_warn "Could not create incident snapshot"
        
        return 0
    else
        log_error "Failed to switch to LIVE"
        return 1
    fi
}

# Function to monitor and create rolling snapshots
monitor_with_snapshots() {
    log_info "Starting monitoring with rolling incident snapshots..."
    
    LAST_SNAPSHOT=$(date +%s)
    SNAPSHOT_INTERVAL=300  # 5 minutes
    
    while true; do
        sleep 30
        
        # Check for risk events
        RISK_EVENTS=$(curl -s localhost:8000/metrics | grep 'trader_risk_blocks_total' | awk '{print $2}' || echo "0")
        
        # Check kill switch
        KILL_SWITCH=$(curl -s localhost:8000/metrics | grep 'trader_kill_switch_total' | awk '{print $2}' || echo "0")
        
        # Create snapshot if risk events increased or kill switch used
        if [ "$RISK_EVENTS" != "0" ] || [ "$KILL_SWITCH" != "0" ]; then
            CURRENT_TIME=$(date +%s)
            if [ $((CURRENT_TIME - LAST_SNAPSHOT)) -ge $SNAPSHOT_INTERVAL ]; then
                TIMESTAMP=$(date +%Y%m%d_%H%M%S)
                python3 -c "
from packages.core.incident_snapshot import snapshot_incident
snapshot_incident('MONITORING_SNAPSHOT', {
    'timestamp': '$(date -u +%Y-%m-%dT%H:%M:%SZ)',
    'risk_events': '$RISK_EVENTS',
    'kill_switch': '$KILL_SWITCH'
})
" 2>/dev/null && log_info "Created monitoring snapshot" || true
                LAST_SNAPSHOT=$CURRENT_TIME
            fi
        fi
    done
}

# Main menu
case "${1:-}" in
    dashboard)
        create_dashboard
        log_info "Dashboard ready. Attach with: tmux attach -t live"
        ;;
    precheck)
        canary_precheck
        ;;
    switch)
        switch_to_live
        ;;
    monitor)
        monitor_with_snapshots
        ;;
    full)
        log_info "Starting full LIVE ops sequence..."
        canary_precheck
        echo ""
        read -p "Pre-check passed. Create dashboard? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            create_dashboard
            log_info "Dashboard created. Attach with: tmux attach -t live"
        fi
        echo ""
        read -p "Ready to switch to LIVE? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            switch_to_live
            log_info "Monitoring started in background"
            monitor_with_snapshots &
        fi
        ;;
    *)
        echo "Usage: $0 {dashboard|precheck|switch|monitor|full}"
        echo ""
        echo "Commands:"
        echo "  dashboard  - Create tmux dashboard"
        echo "  precheck   - Run canary pre-check"
        echo "  switch     - Switch to LIVE mode"
        echo "  monitor    - Start monitoring with snapshots"
        echo "  full       - Run full sequence (precheck → dashboard → switch → monitor)"
        exit 1
        ;;
esac

