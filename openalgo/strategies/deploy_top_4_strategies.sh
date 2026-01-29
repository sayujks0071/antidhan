#!/bin/bash
#
# Deployment Script for Top 4 Strategies
# Generated: 2026-01-29
#
# Strategies to Deploy:
# 1. AI Hybrid Reversion + Breakout (Score: 4.5)
# 2. MCX Commodity Momentum Enhanced (Score: 4.25) - Already running
# 3. Advanced ML Momentum (Score: 4.0)
# 4. SuperTrend VWAP (Score: 3.5)
#

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STRATEGIES_DIR="${SCRIPT_DIR}/scripts"
LOGS_DIR="${SCRIPT_DIR}/logs"
OPENALGO_HOST="${OPENALGO_HOST:-http://127.0.0.1:5001}"
OPENALGO_PORT="${OPENALGO_PORT:-5001}"
OPENALGO_APIKEY="${OPENALGO_APIKEY:-demo_key}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Create logs directory
mkdir -p "${LOGS_DIR}"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Top 4 Strategies Deployment${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Function to check if strategy is running
check_strategy_running() {
    local strategy_name=$1
    pgrep -f "${strategy_name}.py" > /dev/null 2>&1
}

# Function to stop strategy
stop_strategy() {
    local strategy_name=$1
    if check_strategy_running "${strategy_name}"; then
        echo -e "${YELLOW}Stopping ${strategy_name}...${NC}"
        pkill -f "${strategy_name}.py" || true
        sleep 2
        echo -e "${GREEN}✓ ${strategy_name} stopped${NC}"
    else
        echo -e "${BLUE}ℹ ${strategy_name} is not running${NC}"
    fi
}

# Function to start strategy
start_strategy() {
    local strategy_name=$1
    local symbol=$2
    local extra_args=$3
    
    if check_strategy_running "${strategy_name}"; then
        echo -e "${YELLOW}⚠ ${strategy_name} is already running${NC}"
        return 1
    fi
    
    local script_path="${STRATEGIES_DIR}/${strategy_name}.py"
    local log_path="${LOGS_DIR}/${strategy_name}_$(date +%Y%m%d_%H%M%S).log"
    
    if [ ! -f "${script_path}" ]; then
        echo -e "${RED}✗ Strategy file not found: ${script_path}${NC}"
        return 1
    fi
    
    echo -e "${BLUE}Starting ${strategy_name}...${NC}"
    echo -e "  Symbol: ${symbol}"
    echo -e "  Log: ${log_path}"
    
    # Build command based on strategy
    case "${strategy_name}" in
        "ai_hybrid_reversion_breakout")
            cd "${STRATEGIES_DIR}" && nohup python3 "${script_path}" \
                --symbol "${symbol}" \
                --port "${OPENALGO_PORT}" \
                --api_key "${OPENALGO_APIKEY}" \
                ${extra_args} > "${log_path}" 2>&1 &
            ;;
        "advanced_ml_momentum_strategy")
            cd "${STRATEGIES_DIR}" && nohup python3 "${script_path}" \
                --symbol "${symbol}" \
                --port "${OPENALGO_PORT}" \
                --api_key "${OPENALGO_APIKEY}" \
                ${extra_args} > "${log_path}" 2>&1 &
            ;;
        "supertrend_vwap_strategy")
            cd "${STRATEGIES_DIR}" && nohup python3 "${script_path}" \
                --symbol "${symbol}" \
                --quantity 10 \
                --api_key "${OPENALGO_APIKEY}" \
                --host "${OPENALGO_HOST}" \
                ${extra_args} > "${log_path}" 2>&1 &
            ;;
        "mcx_commodity_momentum_strategy")
            # MCX strategy uses different parameters - check existing deployment
            echo -e "${YELLOW}⚠ MCX strategy should be deployed separately${NC}"
            echo -e "${BLUE}  Check existing deployment or use MCX-specific deployment script${NC}"
            return 1
            ;;
        *)
            echo -e "${RED}✗ Unknown strategy: ${strategy_name}${NC}"
            return 1
            ;;
    esac
    
    local pid=$!
    sleep 2
    
    if check_strategy_running "${strategy_name}"; then
        echo -e "${GREEN}✓ ${strategy_name} started successfully (PID: ${pid})${NC}"
        echo "${pid}" > "${LOGS_DIR}/${strategy_name}.pid"
        return 0
    else
        echo -e "${RED}✗ ${strategy_name} failed to start${NC}"
        echo -e "${RED}  Check log: ${log_path}${NC}"
        return 1
    fi
}

# Function to show status
show_status() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}Strategy Status${NC}"
    echo -e "${BLUE}========================================${NC}"
    
    for strategy in "ai_hybrid_reversion_breakout" "advanced_ml_momentum_strategy" "supertrend_vwap_strategy" "mcx_commodity_momentum_strategy"; do
        if check_strategy_running "${strategy}"; then
            local pid=$(pgrep -f "${strategy}.py" | head -1)
            echo -e "${GREEN}✓ ${strategy}${NC} (PID: ${pid})"
        else
            echo -e "${RED}✗ ${strategy}${NC} (Not running)"
        fi
    done
    echo ""
}

# Main deployment logic
main() {
    local action=${1:-deploy}
    
    case "${action}" in
        "deploy")
            echo -e "${BLUE}Deploying Top 4 Strategies...${NC}"
            echo ""
            
            # Strategy 1: AI Hybrid Reversion + Breakout
            echo -e "${BLUE}[1/4] AI Hybrid Reversion + Breakout${NC}"
            stop_strategy "ai_hybrid_reversion_breakout"
            start_strategy "ai_hybrid_reversion_breakout" "NIFTY" "--rsi_lower 30 --sector NIFTY50"
            echo ""
            
            # Strategy 2: MCX Commodity Momentum (Already running - check status)
            echo -e "${BLUE}[2/4] MCX Commodity Momentum Enhanced${NC}"
            if check_strategy_running "mcx_commodity_momentum_strategy"; then
                echo -e "${GREEN}✓ MCX Commodity Momentum is already running${NC}"
            else
                echo -e "${YELLOW}⚠ MCX Commodity Momentum is not running${NC}"
                echo -e "${YELLOW}  Deploy separately using MCX-specific deployment${NC}"
            fi
            echo ""
            
            # Strategy 3: Advanced ML Momentum
            echo -e "${BLUE}[3/4] Advanced ML Momentum${NC}"
            stop_strategy "advanced_ml_momentum_strategy"
            start_strategy "advanced_ml_momentum_strategy" "NIFTY" "--threshold 0.01"
            echo ""
            
            # Strategy 4: SuperTrend VWAP
            echo -e "${BLUE}[4/4] SuperTrend VWAP${NC}"
            stop_strategy "supertrend_vwap_strategy"
            start_strategy "supertrend_vwap_strategy" "NIFTY" "--quantity 10 --sector NIFTYBANK"
            echo ""
            
            show_status
            ;;
            
        "stop")
            echo -e "${YELLOW}Stopping all strategies...${NC}"
            stop_strategy "ai_hybrid_reversion_breakout"
            stop_strategy "advanced_ml_momentum_strategy"
            stop_strategy "supertrend_vwap_strategy"
            stop_strategy "mcx_commodity_momentum_strategy"
            echo ""
            show_status
            ;;
            
        "status")
            show_status
            ;;
            
        "restart")
            echo -e "${BLUE}Restarting all strategies...${NC}"
            $0 stop
            sleep 3
            $0 deploy
            ;;
            
        *)
            echo "Usage: $0 {deploy|stop|status|restart}"
            echo ""
            echo "Commands:"
            echo "  deploy   - Deploy all 4 strategies"
            echo "  stop     - Stop all strategies"
            echo "  status   - Show status of all strategies"
            echo "  restart  - Restart all strategies"
            exit 1
            ;;
    esac
}

# Run main function
main "$@"
