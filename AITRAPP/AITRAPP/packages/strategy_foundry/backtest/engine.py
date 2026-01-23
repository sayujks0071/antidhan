import pandas as pd
import numpy as np
from typing import Dict, List, Any
from packages.strategy_foundry.factory.grammar import StrategyConfig
from packages.strategy_foundry.factory.generator import StrategyGenerator
from packages.strategy_foundry.adapters.core_costs import CostModel
from packages.strategy_foundry.adapters.core_market_hours import MarketHoursAdapter
from packages.strategy_foundry.adapters.core_indicators import IndicatorsAdapter

class BacktestEngine:
    def __init__(self, cost_model: CostModel):
        self.cost_model = cost_model
        self.market_hours = MarketHoursAdapter()
        self.generator = StrategyGenerator()

    def run(self, df: pd.DataFrame, config: StrategyConfig) -> pd.DataFrame:
        """
        Runs the backtest. Returns a DataFrame of trades.
        """
        # 1. Generate Signals (Vectorized)
        # Returns 1 where entry condition is met
        entry_signals = self.generator.generate_signal(df, config)

        # 2. Prepare arrays for fast loop
        opens = df['open'].values
        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values
        times = df['datetime'].values # numpy array of datetime64[ns]

        # ATR for dynamic stops
        # We need ATR series.
        atr_series = IndicatorsAdapter.atr(df, period=14).fillna(0).values

        signal_arr = entry_signals.values

        n = len(df)
        trades = []

        # State
        in_trade = False
        entry_price = 0.0
        entry_idx = 0
        stop_loss = 0.0
        take_profit = 0.0

        # Convert exit time string to time object
        exit_hour, exit_minute = map(int, config.exit_time.split(':'))
        # We need to check time efficiently inside loop.
        # Extract hours/minutes from datetime64 is slightly complex in pure numpy loop without conversion.
        # But we can pre-compute "is_eod" boolean array.

        # Pre-compute EOD exit bar
        # If exit_time is 15:25, and bars are 5m.
        # 15:25 bar starts at 15:25? Or 15:20?
        # Assuming timestamp is bar open time?
        # Usually standard is bar open time.
        # So 15:25 bar (starts 15:25) is the last one?
        # Core hard close is 15:25.
        # So we must be flat by 15:25.
        # Meaning if we are in trade at 15:25, we exit at Open of 15:25 bar? Or Close?
        # If timestamp is Open time:
        # Bar 15:20 -> Closes 15:25. We can exit at Close of 15:20.
        # Bar 15:25 -> Closes 15:30. Too late?
        # Let's say we force exit on the bar that starts >= exit_time (or close to it).

        # Efficient way:
        times_pd = df['datetime']
        # Exit if time >= exit_time
        # We can make a boolean array "force_exit"
        # 15:25 is 15 * 60 + 25 = 925 minutes
        minutes_of_day = times_pd.dt.hour * 60 + times_pd.dt.minute
        exit_minutes = exit_hour * 60 + exit_minute
        force_exit_mask = (minutes_of_day >= exit_minutes).values

        for i in range(1, n):
            # Check Exit first
            if in_trade:
                # 1. EOD Exit (Session Close)
                if force_exit_mask[i]:
                    # Exit at Open of this bar (Market on Open)
                    # because we realized we need to flatten.
                    # Or Close of previous?
                    # "Execution: next bar open".
                    # If we decide at i-1 to exit, we exit at Open i.
                    # But force_exit is a time check.
                    # If time[i] >= 15:25, we exit immediately at Open[i].
                    exit_price = opens[i]
                    self._record_trade(trades, entry_price, exit_price, entry_idx, i, "EOD")
                    in_trade = False
                    continue

                # 2. Time Stop (Max Bars)
                if (i - entry_idx) >= config.max_bars_hold:
                    exit_price = opens[i]
                    self._record_trade(trades, entry_price, exit_price, entry_idx, i, "Time")
                    in_trade = False
                    continue

                # 3. Stop Loss / Take Profit (Intra-bar)
                # We check Low/High of current bar `i`.
                # Assuming we are Long.

                # Check SL (Hit Low)
                if lows[i] <= stop_loss:
                    # Slippage on SL?
                    # We assume execution at stop_loss price (Stop Limit) or worse (Slippage).
                    # Simple model: Exit at stop_loss - slippage (if gap, use Open).
                    # If Open < stop_loss, we gapped down. Exit at Open.
                    if opens[i] < stop_loss:
                        executed_price = opens[i]
                    else:
                        executed_price = stop_loss

                    self._record_trade(trades, entry_price, executed_price, entry_idx, i, "SL")
                    in_trade = False
                    continue

                # Check TP (Hit High)
                if highs[i] >= take_profit:
                    # Limit order filled at TP
                    # If Open > TP, we gapped up. Exit at Open.
                    if opens[i] > take_profit:
                        executed_price = opens[i]
                    else:
                        executed_price = take_profit

                    self._record_trade(trades, entry_price, executed_price, entry_idx, i, "TP")
                    in_trade = False
                    continue

            # Check Entry
            if not in_trade:
                # If Signal at i-1 (completed bar), Enter Open i
                # Check filter/mask? signal_arr already has filters applied.

                if signal_arr[i-1] == 1 and not force_exit_mask[i]:
                    # Enter Long
                    in_trade = True
                    entry_price = opens[i]
                    entry_idx = i

                    # Set Stops
                    atr_val = atr_series[i-1] # Use ATR from signal bar
                    if atr_val == 0 or np.isnan(atr_val):
                         atr_val = entry_price * 0.01

                    stop_loss = entry_price - (config.stop_loss_atr * atr_val)
                    take_profit = entry_price + (config.take_profit_atr * atr_val)

        return pd.DataFrame(trades)

    def _record_trade(self, trades: List, entry_price: float, exit_price: float, entry_idx: int, exit_idx: int, reason: str):
        # Calculate PnL with costs
        # Long only for now

        # Apply slippage
        buy_price = self.cost_model.get_slippage_price(entry_price, 1)
        sell_price = self.cost_model.get_slippage_price(exit_price, -1)

        # Calculate Costs
        entry_cost = self.cost_model.calculate_cost(entry_price, 1, 'BUY') # 1 unit
        exit_cost = self.cost_model.calculate_cost(exit_price, 1, 'SELL')

        # Gross PnL
        gross_pnl = sell_price - buy_price
        # Wait, get_slippage_price adds slippage.
        # Buy at 100 -> pays 100.05
        # Sell at 110 -> receives 109.95
        # PnL = 109.95 - 100.05 = 9.9
        # Correct.

        # Net PnL (subtract brokerage/taxes approx)
        # Cost model calculates absolute cost.
        # But we are calculating per unit price difference?
        # brokerage_per_order is flat. If we trade 1 unit, it's huge.
        # We should calculate % return using "points" logic or assume notional.

        # Let's stick to Points PnL and subtract spread_guard/bps costs.
        # spread_guard is extra penalty.

        # We return percentage return for metrics.
        # return = (sell_price - buy_price) / buy_price

        # Adjust for fixed costs?
        # If we simulate 1 lot (e.g. Nifty 50 qty * 25000 = 12.5L).
        # Brokerage 20 rs is negligible.
        # Main cost is STT/Slippage (BPS).

        # So we can ignore brokerage_per_order for % calculation or convert it to BPS approx.
        # Let's ignore fixed brokerage for simplicity in metrics, rely on BPS.

        net_pnl_points = sell_price - buy_price
        pct_return = net_pnl_points / buy_price

        # Subtract Tax BPS from return?
        # cost_model includes tax_bps.
        # calculate_cost returned absolute.
        # Let's do:
        # PnL = (Exit * (1 - slip - tax)) - (Entry * (1 + slip + tax))
        # This double counts tax if tax is on turnover.
        # STT is on Sell (0.025%) for Futures? Or 0.1% Equity?
        # Let's use `slippage_bps` + `tax_bps` as total friction.

        # My `get_slippage_price` only used `slippage_bps`.
        # I should add `tax_bps` to friction.

        total_friction_bps = self.cost_model.slippage_bps + self.cost_model.tax_bps

        # Effective Entry = Price * (1 + friction)
        eff_entry = entry_price * (1 + total_friction_bps/10000.0)
        # Effective Exit = Price * (1 - friction)
        eff_exit = exit_price * (1 - total_friction_bps/10000.0)

        net_ret = (eff_exit - eff_entry) / eff_entry

        trades.append({
            "entry_idx": entry_idx,
            "exit_idx": exit_idx,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "net_return": net_ret,
            "reason": reason,
            "bars_held": exit_idx - entry_idx
        })
