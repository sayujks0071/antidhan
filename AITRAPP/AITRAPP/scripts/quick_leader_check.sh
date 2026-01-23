#!/usr/bin/env bash
# Quick leader lock + supervisor status check (for dashboard/tmux)

API="${API:-http://localhost:8000}"

echo "=== Leadership & Supervisor Status ==="
echo ""

# Leader lock
LEADER=$(curl -s "$API/metrics" 2>/dev/null | awk '/^trader_is_leader[^_]/ {print $2; exit}' || echo "0")
if [[ "$LEADER" == "1" ]]; then
    echo "✅ Leader: ACQUIRED ($LEADER)"
else
    echo "❌ Leader: NOT ACQUIRED ($LEADER)"
fi

# Supervisor state
SUPERVISOR_STATE=$(curl -s "$API/metrics" 2>/dev/null | awk '/^trader_scan_supervisor_state/ {print $2; exit}' || echo "0")
STATE_LABEL="unknown"
case "${SUPERVISOR_STATE%.*}" in
    0) STATE_LABEL="stopped" ;;
    1) STATE_LABEL="running" ;;
    2) STATE_LABEL="done" ;;
    3) STATE_LABEL="exception" ;;
    4) STATE_LABEL="stopping" ;;
esac

if [[ "$SUPERVISOR_STATE" == "1" ]]; then
    echo "✅ Supervisor: $STATE_LABEL ($SUPERVISOR_STATE)"
else
    echo "⚠️  Supervisor: $STATE_LABEL ($SUPERVISOR_STATE)"
fi

# Scan ticks
TICKS=$(curl -s "$API/metrics" 2>/dev/null | awk '/^trader_scan_ticks_total/ {print $2; exit}' || echo "0")
echo "📊 Scan Ticks: ${TICKS%.0f}"

# Heartbeats
MD_HB=$(curl -s "$API/metrics" 2>/dev/null | awk '/^trader_marketdata_heartbeat_seconds[^_]/ {print $2; exit}' || echo "999")
ORDER_HB=$(curl -s "$API/metrics" 2>/dev/null | awk '/^trader_order_stream_heartbeat_seconds[^_]/ {print $2; exit}' || echo "999")
SCAN_HB=$(curl -s "$API/metrics" 2>/dev/null | awk '/^trader_scan_heartbeat_seconds[^_]/ {print $2; exit}' || echo "999")

echo ""
echo "=== Heartbeats ==="
printf "Market Data:   %.2fs %s\n" "$MD_HB" "$([ $(echo "$MD_HB < 5" | bc -l 2>/dev/null || echo 0) -eq 1 ] && echo '✅' || echo '❌')"
printf "Order Stream:  %.2fs %s\n" "$ORDER_HB" "$([ $(echo "$ORDER_HB < 5" | bc -l 2>/dev/null || echo 0) -eq 1 ] && echo '✅' || echo '❌')"
printf "Scan Loop:     %.2fs %s\n" "$SCAN_HB" "$([ $(echo "$SCAN_HB < 5" | bc -l 2>/dev/null || echo 0) -eq 1 ] && echo '✅' || echo '❌')"

