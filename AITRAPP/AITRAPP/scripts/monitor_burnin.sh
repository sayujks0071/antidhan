#!/usr/bin/env bash
# Simple monitoring script for burn-in (no tmux required)
set -euo pipefail

API="${API:-http://localhost:8000}"

echo "📊 Burn-In Monitoring"
echo "===================="
echo ""
echo "Press Ctrl+C to stop"
echo ""

while true; do
    clear
    echo "📊 Burn-In Monitoring - $(date '+%Y-%m-%d %H:%M:%S')"
    echo "=========================================="
    echo ""
    
    # Orchestrator state
    echo "🔍 Orchestrator State:"
    STATE=$(curl -s "${API}/state" 2>/dev/null || echo "{}")
    echo "$STATE" | jq '{running:.running, paused:.is_paused, positions:(.positions_count // (.positions | length) // 0)}' 2>/dev/null || echo "   ⚠️  State not available"
    echo ""
    
    # Key metrics
    echo "📈 Key Metrics:"
    METRICS=$(curl -s "${API}/metrics" 2>/dev/null | grep -E "^trader_(is_leader|signals_total|decisions_total|orders_placed_total|oco_children_created_total|marketdata_heartbeat_seconds|order_stream_heartbeat_seconds|kill_switch_total)" || echo "")
    
    if [ -n "$METRICS" ]; then
        echo "$METRICS" | while IFS= read -r line; do
            METRIC_NAME=$(echo "$line" | awk '{print $1}')
            METRIC_VALUE=$(echo "$line" | awk '{print $2}')
            
            case "$METRIC_NAME" in
                trader_is_leader)
                    if [ "$METRIC_VALUE" = "1" ]; then
                        echo "   ✅ $METRIC_NAME = $METRIC_VALUE"
                    else
                        echo "   ⚠️  $METRIC_NAME = $METRIC_VALUE"
                    fi
                    ;;
                trader_marketdata_heartbeat_seconds|trader_order_stream_heartbeat_seconds)
                    VAL=$(echo "$METRIC_VALUE" | awk '{print int($1)}' 2>/dev/null || echo "999")
                    if [ "$VAL" -lt 5 ]; then
                        echo "   ✅ $METRIC_NAME = ${METRIC_VALUE}s"
                    else
                        echo "   ⚠️  $METRIC_NAME = ${METRIC_VALUE}s (stale)"
                    fi
                    ;;
                *)
                    echo "   📊 $METRIC_NAME = $METRIC_VALUE"
                    ;;
            esac
        done
    else
        echo "   ⚠️  Metrics not available yet"
    fi
    echo ""
    
    # Positions
    echo "💼 Positions:"
    POSITIONS=$(curl -s "${API}/positions" 2>/dev/null | jq '.count // (.positions | length) // 0' 2>/dev/null || echo "0")
    echo "   Open: $POSITIONS"
    echo ""
    
    echo "Refresh in 5 seconds... (Ctrl+C to stop)"
    sleep 5
done

