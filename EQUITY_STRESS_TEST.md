# Equity Curve Stress Test

## Overview
Reconstructed the monthly equity curve from the generated execution logs (SuperTrendVWAP, AdvancedMLMomentum, GapFadeStrategy).

## Findings
- **Worst Day**: 2026-03-05
- **PnL on Worst Day**: 769.00 (Total). Although the overall daily PnL was positive, the `GapFadeStrategy` significantly dragged the portfolio down with a loss of -512.00.

## Root Cause Analysis
The primary source of the drawdown on the Worst Day was the `GapFadeStrategy`. After inspecting the simulated performance profile and memory artifacts, it was determined that the strategy logic repeatedly failed due to **Gap-Up/Trend Persistence**.
- **Issue**: The strategy attempts to fade opening gaps based on Reversal Candle confirmation.
- **Environment**: On high-IV, strong trend days, the "Reversal Candle" often turns out to be a minor pullback before the trend continues, resulting in the strategy hitting its Stop-Loss.
