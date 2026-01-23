#!/bin/bash
# Post-close hygiene - run daily at 15:30 IST

set -e

DATE=$(date +%Y-%m-%d)
REPORTS_DIR="reports/$DATE"
mkdir -p "$REPORTS_DIR"

echo "📦 Post-Close Hygiene - $DATE"
echo ""

# 1. DB snapshot
echo "1️⃣ Creating DB snapshot..."
pg_dump $DATABASE_URL > "$REPORTS_DIR/db_snapshot_$DATE.sql"
echo "   ✅ Snapshot saved: $REPORTS_DIR/db_snapshot_$DATE.sql"
echo ""

# 2. Tar logs + report
echo "2️⃣ Archiving logs and report..."
tar -czf "$REPORTS_DIR/logs_and_report_$DATE.tar.gz" \
    logs/ \
    burnin-report-*.txt 2>/dev/null || true
echo "   ✅ Archive created: $REPORTS_DIR/logs_and_report_$DATE.tar.gz"
echo ""

# 2.5. Latency summary (if API is running)
if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
    echo "2.5️⃣ Printing latency histogram..."
    bash scripts/print_latency_histogram.sh > "$REPORTS_DIR/latency_summary_$DATE.txt" 2>&1 || true
    echo "   ✅ Latency summary saved: $REPORTS_DIR/latency_summary_$DATE.txt"
fi
echo ""

# 3. Record config SHA, git SHA, and metrics
echo "3️⃣ Recording system state..."
{
    echo "Date: $DATE"
    echo "Config SHA: $(python -c 'from packages.core.config import app_config; print(getattr(app_config, "config_sha", "unknown"))' 2>/dev/null || echo "unknown")"
    echo "Git SHA: $(git rev-parse HEAD 2>/dev/null || echo "unknown")"
    echo ""
    echo "Top Metrics (Prometheus scrape):"
    curl -s localhost:8000/metrics | grep -E "^trader_(signals_total|decisions_total|orders_placed_total|orders_filled_total|portfolio_heat_rupees|daily_pnl_rupees)" | head -20 || echo "Metrics unavailable"
} > "$REPORTS_DIR/system_state_$DATE.txt"
echo "   ✅ System state saved: $REPORTS_DIR/system_state_$DATE.txt"
echo ""

# 4. Rotate access token (if required)
echo "4️⃣ Token rotation check..."
if [ -n "$KITE_TOKEN_ROTATE_DAILY" ] && [ "$KITE_TOKEN_ROTATE_DAILY" = "true" ]; then
    echo "   ⚠️  Token rotation required (update .env manually)"
else
    echo "   ✅ Token rotation not required"
fi
echo ""

# 5. Tag release
echo "5️⃣ Tagging release..."
git tag burnin-$(date +%Y-%m-%d) 2>/dev/null || echo "   ⚠️  Git tag failed (not a git repo?)"
echo "   ✅ Tag created: burnin-$(date +%Y-%m-%d)"
echo ""

echo "✅ Post-close hygiene complete"
echo "📁 Reports saved to: $REPORTS_DIR"
echo ""
echo "Next: git push --tags (if using git)"

