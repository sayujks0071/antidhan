#!/usr/bin/env python3
"""
IC Pre-Entry Quality Check — run at 9:10 AM before Wave 1
=========================================================
Checks regime, VIX, net credit, margin, and gap before allowing IC entry.

Exit codes:
  0 = GO      — all conditions met, proceed with Wave 1
  1 = CAUTION — partial conditions met, reduce lots or wait
  2 = SKIP    — do not trade today (trending, high VIX chop, or thin premium)

Usage:
  python3 ic_pre_entry.py
  python3 ic_pre_entry.py && echo "Proceeding with Wave 1..."
"""

import sys
import requests
import pytz
from datetime import datetime

# ── Config — single source of truth ─────────────────────────────────────────
from ic_config import OPENALGO_KEY as KEY, OPENALGO_URL as _API_BASE, \
                      get_next_expiry, LOT_SIZE, SPAN_PER_LOT as SPAN_MARGIN
API    = _API_BASE
EXPIRY = get_next_expiry()   # auto-computes each run — no more manual weekly updates

MIN_CREDIT        = 20     # ₹/unit: below this → SKIP
CREDIT_CAUTION    = 15     # ₹/unit: below this but ≥10 → CAUTION
GAP_SKIP_PCT      = 1.5    # NIFTY gap > this % from session open vs prev ATM → wait
VIX_HIGH_SKIP     = 18     # VIX > this with VOLATILE_CHOP → SKIP
VIX_CHOP_CAUTION  = 14     # VIX 14–18 with VOLATILE_CHOP → CAUTION

IST = pytz.timezone("Asia/Kolkata")

# ── Helpers ──────────────────────────────────────────────────────────────────

def post(endpoint, payload, timeout=8):
    try:
        r = requests.post(f"{API}/{endpoint}", json=payload, timeout=timeout)
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def get_option_chain(expiry, strike_count=10):
    return post("optionchain", {
        "apikey": KEY, "underlying": "NIFTY",
        "exchange": "NSE_INDEX", "expiry_date": expiry,
        "strike_count": strike_count
    })


def get_vix():
    """Attempt to fetch India VIX via optionchain; return 14.0 if unavailable."""
    try:
        rv = post("optionchain", {
            "apikey": KEY, "underlying": "INDIAVIX",
            "exchange": "NSE_INDEX", "expiry_date": EXPIRY,
            "strike_count": 1
        }, timeout=5)
        v = float(rv.get("underlying_ltp", 0) or 0)
        return v if v > 0 else 14.0
    except Exception:
        return 14.0


def get_funds():
    resp = post("funds", {"apikey": KEY})
    return float(resp.get("data", {}).get("availablecash", 0) or 0)


def detect_regime():
    """Call RegimeDetector from OpenClaw skills; fallback to 'UNKNOWN' on error."""
    try:
        sys.path.insert(0, "/Users/mac/.openclaw/workspace/skills/market-regime/helpers")
        from regime_detector import RegimeDetector
        result = RegimeDetector().detect_regime("NIFTY", "NSE_INDEX")
        return result.get("regime", "UNKNOWN"), result.get("position_sizing_factor", 1.0)
    except Exception as e:
        print(f"  ⚠️  Regime detector error: {e}")
        return "UNKNOWN", 1.0


def compute_wave_lots(avail, vix_factor=1.0):
    """Mirror ic_monitor.py compute_wave_lots logic."""
    max_lots = int(avail * 0.78 / SPAN_MARGIN)
    wave1    = max(4, min(40, int(max_lots * vix_factor)))
    wave2    = max(4, min(40, int(wave1 * 0.65)))
    wave3    = max(4, min(40, int(wave1 * 0.40)))
    return wave1, wave2, wave3


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    now = datetime.now(IST)
    print(f"\n{'='*60}")
    print(f"  IC PRE-ENTRY CHECK — {now.strftime('%d-%b-%Y %H:%M IST')}")
    print(f"  Expiry: {EXPIRY}")
    print(f"{'='*60}")

    reasons_skip    = []
    reasons_caution = []

    # ── 1. Fetch option chain ────────────────────────────────────────────────
    print("\n[1/6] Fetching option chain...")
    oc = get_option_chain(EXPIRY, strike_count=10)
    if "error" in oc:
        print(f"  ❌ Option chain error: {oc['error']}")
        print("  → Cannot proceed without market data.")
        print("\n  ⛔  VERDICT: SKIP  (API unavailable — no market data)")
        sys.exit(2)

    nifty = float(oc.get("underlying_ltp", 0) or 0)
    atm   = float(oc.get("atm_strike", 0) or 0)

    if nifty <= 0 or atm <= 0:
        print("  ❌ NIFTY or ATM is 0 — market may not be open yet.")
        print("\n  ⛔  VERDICT: SKIP  (market not open or pre-open)")
        sys.exit(2)

    print(f"  NIFTY: {nifty:.1f}  |  ATM: {atm:.0f}")

    # ── 2. VIX ───────────────────────────────────────────────────────────────
    print("\n[2/6] Fetching India VIX...")
    vix = get_vix()
    print(f"  VIX: {vix:.2f}")

    # VIX-based lot sizing factor
    if vix > 20:
        vix_factor = 0.5
        print("  ⚠️  VIX > 20: reduce lots 50%, consider widening to ±150/±300")
    elif vix > 16:
        vix_factor = 0.75
        print("  ⚠️  VIX 16–20: reduce lots 25%")
    elif vix < 12:
        vix_factor = 0.0
        print("  ⚠️  VIX < 12: premium too thin — IC not viable")
        reasons_skip.append(f"VIX {vix:.1f} < 12 (premium too thin for IC)")
    else:
        vix_factor = 1.0

    # ── 3. Regime detection ──────────────────────────────────────────────────
    print("\n[3/6] Detecting market regime...")
    regime, sizing_factor = detect_regime()
    print(f"  Regime: {regime}  |  Sizing factor: {sizing_factor:.2f}")

    if regime in ("TRENDING_BULL", "TRENDING_BEAR"):
        reasons_skip.append(f"Regime {regime} — directional momentum kills IC")
    elif regime == "VOLATILE_CHOP":
        if vix > VIX_HIGH_SKIP:
            reasons_skip.append(f"VOLATILE_CHOP + VIX {vix:.1f} > {VIX_HIGH_SKIP} — random direction + high IV")
        elif vix > VIX_CHOP_CAUTION:
            reasons_caution.append(f"VOLATILE_CHOP + VIX {vix:.1f} (14–18) — use 60% lots")
        else:
            reasons_caution.append(f"VOLATILE_CHOP + VIX {vix:.1f} ≤ 14 — mild chop, watch closely")
    elif regime == "MEAN_REVERSION":
        print("  ✅ MEAN_REVERSION — ideal IC regime")
    else:
        reasons_caution.append(f"Regime '{regime}' unknown — proceed with caution")

    # ── 4. Net credit check ──────────────────────────────────────────────────
    print("\n[4/6] Computing net credit from option chain...")
    chain = oc.get("chain", [])

    # Extract premiums for ATM±100 (short) and ATM±200 (long)
    short_ce_ltp = short_pe_ltp = long_ce_ltp = long_pe_ltp = 0.0
    targets = {
        int(atm + 100): "short_ce",
        int(atm - 100): "short_pe",
        int(atm + 200): "long_ce",
        int(atm - 200): "long_pe",
    }
    for s in chain:
        strike = int(s.get("strike", 0))
        if strike in targets:
            key_name = targets[strike]
            if key_name == "short_ce":
                short_ce_ltp = float(s.get("ce", {}).get("ltp", 0) or 0)
            elif key_name == "short_pe":
                short_pe_ltp = float(s.get("pe", {}).get("ltp", 0) or 0)
            elif key_name == "long_ce":
                long_ce_ltp = float(s.get("ce", {}).get("ltp", 0) or 0)
            elif key_name == "long_pe":
                long_pe_ltp = float(s.get("pe", {}).get("ltp", 0) or 0)

    net_credit = (short_ce_ltp + short_pe_ltp) - (long_ce_ltp + long_pe_ltp)

    print(f"  Short CE ({int(atm+100)}): ₹{short_ce_ltp:.2f}")
    print(f"  Short PE ({int(atm-100)}): ₹{short_pe_ltp:.2f}")
    print(f"  Long  CE ({int(atm+200)}): ₹{long_ce_ltp:.2f}")
    print(f"  Long  PE ({int(atm-200)}): ₹{long_pe_ltp:.2f}")
    print(f"  Net credit:  ₹{net_credit:.2f}/unit")

    if net_credit < 10:
        reasons_skip.append(f"Net credit ₹{net_credit:.2f} < ₹10 — not enough premium")
    elif net_credit < MIN_CREDIT:
        reasons_caution.append(f"Net credit ₹{net_credit:.2f} < ₹{MIN_CREDIT} target (thin premium)")

    # ── 5. Margin & lot sizing ───────────────────────────────────────────────
    print("\n[5/6] Checking margin & lot sizing...")
    avail = get_funds()
    effective_vix_factor = vix_factor * sizing_factor
    wave1, wave2, wave3 = compute_wave_lots(avail, effective_vix_factor)
    margin_needed = wave1 * SPAN_MARGIN

    print(f"  Available cash:  ₹{avail:,.0f}")
    print(f"  VIX factor:      {vix_factor:.2f}  |  Regime factor: {sizing_factor:.2f}")
    print(f"  Wave 1 lots:     {wave1}  ({wave1 * LOT_SIZE} qty/leg)  — margin ₹{margin_needed:,.0f}")
    print(f"  Wave 2 lots:     {wave2}  ({wave2 * LOT_SIZE} qty/leg)")
    print(f"  Wave 3 lots:     {wave3}  ({wave3 * LOT_SIZE} qty/leg)")

    if wave1 < 4:
        reasons_skip.append(f"Insufficient margin — only {wave1} lots possible (need ≥4)")
    elif avail < margin_needed:
        reasons_caution.append(f"Margin tight: ₹{avail:,.0f} available vs ₹{margin_needed:,.0f} needed")

    # ── 6. Gap check ─────────────────────────────────────────────────────────
    print("\n[6/6] Gap check...")
    gap_pct = abs(nifty - atm) / atm * 100 if atm > 0 else 0
    print(f"  NIFTY {nifty:.1f} vs ATM {atm:.0f} → gap: {gap_pct:.2f}%")
    if gap_pct > GAP_SKIP_PCT:
        reasons_caution.append(
            f"NIFTY gapping {gap_pct:.1f}% from ATM — consider waiting 15–20 min for settlement"
        )

    # ── Verdict ──────────────────────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print("  SUMMARY")
    print(f"{'─'*60}")

    if reasons_skip:
        verdict   = "SKIP"
        exit_code = 2
        icon      = "🔴"
    elif reasons_caution:
        verdict   = "CAUTION"
        exit_code = 1
        icon      = "🟡"
    else:
        verdict   = "GO"
        exit_code = 0
        icon      = "🟢"

    if reasons_skip:
        print("  SKIP reasons:")
        for r in reasons_skip:
            print(f"    ✗ {r}")
    if reasons_caution:
        print("  CAUTION reasons:")
        for r in reasons_caution:
            print(f"    ⚠  {r}")
    if not reasons_skip and not reasons_caution:
        print("  ✅ All conditions met")

    print()
    print(f"  {icon}  VERDICT: {verdict}")
    if verdict == "GO":
        print(f"     → Proceed with Wave 1: {wave1} lots × {LOT_SIZE} = {wave1*LOT_SIZE} qty/leg")
        print(f"     → Expected P&L: ₹{int(wave1*LOT_SIZE*net_credit*0.7):,}–₹{int(wave1*LOT_SIZE*net_credit*0.9):,}")
    elif verdict == "CAUTION":
        reduced = max(4, int(wave1 * 0.6))
        print(f"     → Consider {reduced} lots instead of {wave1} (60% position)")
        print("     → Widen strikes to ±150/±300 if VIX > 16")
    else:
        print("     → Do NOT enter IC today")

    print(f"\n  Expiry: {EXPIRY} | Strikes: {int(atm-100)}PE/{int(atm+100)}CE (short) | {int(atm-200)}PE/{int(atm+200)}CE (long)")
    print(f"{'='*60}\n")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
