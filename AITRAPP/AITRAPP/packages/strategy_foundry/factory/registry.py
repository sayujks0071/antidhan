import json
import os
from typing import List
from packages.strategy_foundry.factory.grammar import StrategyConfig, Rule, Filter

class CandidateRegistry:
    @staticmethod
    def save_candidates(candidates: List[StrategyConfig], filepath: str):
        data = [c.to_dict() for c in candidates]
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)

    @staticmethod
    def load_candidates(filepath: str) -> List[StrategyConfig]:
        if not os.path.exists(filepath):
            return []

        with open(filepath, 'r') as f:
            data = json.load(f)

        candidates = []
        for item in data:
            entry_rules = [Rule(**r) for r in item['entry_rules']]
            filters = [Filter(**f) for f in item.get('filters', [])]

            c = StrategyConfig(
                strategy_id=item['strategy_id'],
                entry_rules=entry_rules,
                filters=filters,
                stop_loss_atr=item['stop_loss_atr'],
                take_profit_atr=item['take_profit_atr'],
                trailing_stop_atr=item.get('trailing_stop_atr'),
                max_bars_hold=item['max_bars_hold'],
                exit_time=item.get('exit_time', "15:25")
            )
            candidates.append(c)
        return candidates
