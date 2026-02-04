import json
import logging
from datetime import datetime, timedelta

import pytz

from packages.strategy_foundry.adapters.core_indicators import IndicatorsAdapter
from packages.strategy_foundry.adapters.core_market_hours import MarketHoursAdapter
from packages.strategy_foundry.data.loader import DataLoader
from packages.strategy_foundry.factory.generator import StrategyGenerator
from packages.strategy_foundry.factory.grammar import Filter, Rule, StrategyConfig
from packages.strategy_foundry.selection.champion_store import ChampionStore

logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")

class SignalPublisher:
    def __init__(self, instrument: str, timeframe: str = "5m"):
        self.instrument = instrument
        self.timeframe = timeframe # Champion store key
        # If timeframe is 'blended', we default to '5m' for data execution
        self.data_timeframe = "5m" if timeframe == "blended" else timeframe

        self.store = ChampionStore()
        self.loader = DataLoader()
        self.generator = StrategyGenerator()
        self.market_hours = MarketHoursAdapter()
        self.output_path = "packages/strategy_foundry/results/live_signal.json"

    def publish(self):
        """
        Generates and publishes signal JSON if conditions met.
        """
        # 1. Check Market Hours
        if not self.market_hours.is_market_open():
            self._write_skipped("MarketClosed")
            return

        # 2. Load Champion
        champion = self.store.get_current_champion(self.instrument, self.timeframe)
        if not champion:
            self._write_skipped("NoChampion")
            return

        # Reconstruct StrategyConfig
        strat_data = champion['strategy_config']
        config = StrategyConfig(
            strategy_id=strat_data['strategy_id'],
            entry_rules=[Rule(**r) for r in strat_data['entry_rules']],
            filters=[Filter(**f) for f in strat_data['filters']],
            stop_loss_atr=strat_data['stop_loss_atr'],
            take_profit_atr=strat_data['take_profit_atr'],
            trailing_stop_atr=strat_data.get('trailing_stop_atr'),
            max_bars_hold=strat_data['max_bars_hold'],
            exit_time=strat_data.get('exit_time', "15:25")
        )

        # 3. Load Data (Force Download for Freshness)
        df = self.loader.get_data(self.instrument, self.data_timeframe, force_download=True)
        if df is None or df.empty:
            self._write_skipped("NoData")
            return

        # 4. Generate Signal
        # We need the full series to calculate indicators correctly
        signals = self.generator.generate_signal(df, config)

        # Get latest completed bar
        # Assuming last row is the latest available bar.
        # Check timestamp freshness.
        last_dt = df['datetime'].iloc[-1]
        now = datetime.now(IST)

        # If last bar is too old (> 30 mins), warn/skip?
        # For Yahoo, delay is expected. But >30m means market closed or feed dead.
        if (now - last_dt) > timedelta(minutes=45):
            self._write_skipped("DataStale")
            return

        # Signal at Close of T is for Open of T+1
        # Check signal at iloc[-1]
        raw_signal = int(signals.iloc[-1])

        # We also need to check Exits (Flat by 15:25)
        # Managed by core/execution usually, but we should signal "FLAT" if near close.
        if (now.time() >= self.market_hours.get_hard_close_time()):
            signal_val = 0 # Flat
            reason = "HardClose"
        else:
            signal_val = raw_signal
            reason = "StrategySignal"

        # Proxies
        proxies = self.loader.instrument_map.get('live_proxy', {})
        live_proxy = proxies.get(self.instrument, "")
        paper_proxies = self.loader.instrument_map.get('paper_proxy', {})
        paper_proxy = paper_proxies.get(self.instrument, "")

        # Calculate Risk Params (Dynamic ATR)
        atr_series = IndicatorsAdapter.atr(df, period=14)
        current_atr = float(atr_series.iloc[-1])

        stop_loss_dist = config.stop_loss_atr * current_atr
        take_profit_dist = config.take_profit_atr * current_atr

        payload = {
            "timestamp_ist": now.isoformat(),
            "data_timestamp": last_dt.isoformat(),
            "champion_id": config.strategy_id,
            "timeframe": self.timeframe,
            "instrument": self.instrument,
            "proxy_symbol_paper": paper_proxy,
            "proxy_symbol_live": live_proxy,
            "signal": signal_val,
            "rule_summary": f"Entry: {len(config.entry_rules)} rules",
            "risk": {
                "stop_loss_dist": stop_loss_dist,
                "take_profit_dist": take_profit_dist,
                "flat_by": config.exit_time
            },
            "status": "OK",
            "reason": reason
        }

        self._write_json(payload)
        logger.info(f"Published signal for {self.instrument}: {signal_val}")

    def _write_skipped(self, reason: str):
        payload = {
            "timestamp_ist": datetime.now(IST).isoformat(),
            "status": "SKIPPED",
            "reason": reason
        }
        self._write_json(payload)
        logger.info(f"Skipped signal publishing: {reason}")

    def _write_json(self, payload: dict):
        with open(self.output_path, 'w') as f:
            json.dump(payload, f, indent=2)

if __name__ == "__main__":
    # Test
    pub = SignalPublisher("NIFTY", "5m")
    pub.publish()
