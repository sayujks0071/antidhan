import logging
from typing import Dict

from packages.strategy_foundry.selection.champion_store import ChampionStore

logger = logging.getLogger(__name__)

class Promoter:
    def __init__(self, instrument: str, timeframe: str):
        self.instrument = instrument
        self.timeframe = timeframe
        self.store = ChampionStore()

    def check_and_promote(self, challenger: Dict) -> bool:
        """
        Checks if challenger beats current champion.
        challenger: Dict from Ranker (row of dataframe)
        """
        current = self.store.get_current_champion(self.instrument, self.timeframe)

        if not current:
            logger.info(f"No current champion for {self.instrument} {self.timeframe}. Promoting challenger.")
            self.store.save_champion(self.instrument, self.timeframe, challenger)
            return True

        # Comparison Logic
        # 1. Score Improvement >= 10%
        score_diff = (challenger['score'] - current['score']) / abs(current['score'])

        # 2. DD Reduction >= 5% absolute (e.g. 0.20 -> 0.15)
        dd_diff = current['avg_max_dd'] - challenger['avg_max_dd']

        # 3. Sharpe Non-Degradation (within 5%)
        sharpe_ratio = challenger['avg_sharpe'] / current['avg_sharpe'] if current['avg_sharpe'] != 0 else 1.0

        should_promote = False
        reason = ""

        if score_diff >= 0.10:
            should_promote = True
            reason = f"Score improved by {score_diff:.2%}"
        elif dd_diff >= 0.05 and sharpe_ratio >= 0.95:
            should_promote = True
            reason = f"Drawdown reduced by {dd_diff:.2%} without Sharpe degradation"

        if should_promote:
            logger.info(f"Promoting new champion for {self.instrument} {self.timeframe}: {reason}")
            self.store.save_champion(self.instrument, self.timeframe, challenger)
            return True

        return False
