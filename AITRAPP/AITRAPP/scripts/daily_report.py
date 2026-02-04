#!/usr/bin/env python3
"""Generate daily trading report from database"""
import argparse
from datetime import date, datetime
from typing import Optional

from packages.storage.database import get_db_session
from packages.storage.models import Decision, Order, Position, RiskEvent, Signal, Trade


def generate_report(report_date: Optional[date] = None):
    """Generate daily trading report"""
    if not report_date:
        report_date = date.today()

    print(f"\n{'='*60}")
    print(f"Daily Trading Report - {report_date}")
    print(f"{'='*60}\n")

    with get_db_session() as db:
        # Signals
        signals = db.query(Signal).filter(
            Signal.ts >= datetime.combine(report_date, datetime.min.time()),
            Signal.ts < datetime.combine(report_date, datetime.max.time()) + datetime.timedelta(days=1)
        ).all()

        print(f"📊 Signals Generated: {len(signals)}")
        strategy_counts = {}
        for s in signals:
            strategy_counts[s.strategy] = strategy_counts.get(s.strategy, 0) + 1
        for strategy, count in strategy_counts.items():
            print(f"   - {strategy}: {count}")

        # Decisions
        decisions = db.query(Decision).filter(
            Decision.ts >= datetime.combine(report_date, datetime.min.time()),
            Decision.ts < datetime.combine(report_date, datetime.max.time()) + datetime.timedelta(days=1)
        ).all()

        approved = [d for d in decisions if d.status.value == "PLANNED"]
        rejected = [d for d in decisions if d.status.value == "REJECTED"]

        print(f"\n🎯 Decisions: {len(decisions)}")
        print(f"   - Approved: {len(approved)}")
        print(f"   - Rejected: {len(rejected)}")

        # Orders
        orders = db.query(Order).filter(
            Order.ts >= datetime.combine(report_date, datetime.min.time()),
            Order.ts < datetime.combine(report_date, datetime.max.time()) + datetime.timedelta(days=1)
        ).all()

        filled = [o for o in orders if o.status.value == "FILLED"]
        print(f"\n📦 Orders: {len(orders)}")
        print(f"   - Filled: {len(filled)}")

        # Positions
        positions = db.query(Position).filter(
            Position.opened_at >= datetime.combine(report_date, datetime.min.time()),
            Position.opened_at < datetime.combine(report_date, datetime.max.time()) + datetime.timedelta(days=1)
        ).all()

        open_positions = [p for p in positions if p.status.value == "OPEN"]
        closed_positions = [p for p in positions if p.status.value == "CLOSED"]

        print(f"\n💼 Positions: {len(positions)}")
        print(f"   - Open: {len(open_positions)}")
        print(f"   - Closed: {len(closed_positions)}")

        # Trades
        trades = db.query(Trade).filter(
            Trade.ts >= datetime.combine(report_date, datetime.min.time()),
            Trade.ts < datetime.combine(report_date, datetime.max.time()) + datetime.timedelta(days=1)
        ).all()

        total_pnl = sum([t.net_pnl for t in trades])
        winning_trades = [t for t in trades if t.net_pnl > 0]
        losing_trades = [t for t in trades if t.net_pnl <= 0]

        print(f"\n💰 Trades: {len(trades)}")
        print(f"   - Winners: {len(winning_trades)}")
        print(f"   - Losers: {len(losing_trades)}")
        print(f"   - Total P&L: ₹{total_pnl:,.2f}")

        if trades:
            avg_win = sum([t.net_pnl for t in winning_trades]) / len(winning_trades) if winning_trades else 0
            avg_loss = sum([t.net_pnl for t in losing_trades]) / len(losing_trades) if losing_trades else 0
            print(f"   - Avg Win: ₹{avg_win:,.2f}")
            print(f"   - Avg Loss: ₹{avg_loss:,.2f}")
            if avg_loss != 0:
                print(f"   - Win/Loss Ratio: {abs(avg_win / avg_loss):.2f}")

        # Risk Events
        risk_events = db.query(RiskEvent).filter(
            RiskEvent.ts >= datetime.combine(report_date, datetime.min.time()),
            RiskEvent.ts < datetime.combine(report_date, datetime.max.time()) + datetime.timedelta(days=1)
        ).all()

        print(f"\n⚠️  Risk Events: {len(risk_events)}")
        for event in risk_events[:10]:  # Show first 10
            print(f"   - {event.event_type}: {event.message}")

        # Portfolio Heat Timeline (simplified)
        print("\n📈 Portfolio Heat Timeline:")
        print(f"   - Max Heat: {max([d.portfolio_heat_after or 0 for d in decisions]) if decisions else 0:.2f}%")

        print(f"\n{'='*60}\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate daily trading report")
    parser.add_argument("--date", type=str, help="Date in YYYY-MM-DD format (default: today)")

    args = parser.parse_args()

    report_date = None
    if args.date:
        report_date = datetime.strptime(args.date, "%Y-%m-%d").date()

    generate_report(report_date)

