import json
import os
from datetime import datetime
from typing import Dict, Optional


class ChampionStore:
    def __init__(self, base_dir: str = "packages/strategy_foundry/results/champions"):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)

    def get_current_champion(self, instrument: str, timeframe: str) -> Optional[Dict]:
        path = os.path.join(self.base_dir, f"current_{instrument}_{timeframe}.json")
        if not os.path.exists(path):
            return None
        with open(path, 'r') as f:
            return json.load(f)

    def save_champion(self, instrument: str, timeframe: str, candidate_data: Dict):
        # 1. Archive old champion if exists
        current = self.get_current_champion(instrument, timeframe)
        if current:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            old_id = current.get('strategy_id', 'unknown')
            archive_path = os.path.join(self.base_dir, f"archive_{instrument}_{timeframe}_{ts}_{old_id}.json")
            with open(archive_path, 'w') as f:
                json.dump(current, f, indent=2)

        # 2. Save new champion
        path = os.path.join(self.base_dir, f"current_{instrument}_{timeframe}.json")
        candidate_data['promoted_at'] = datetime.now().isoformat()
        with open(path, 'w') as f:
            json.dump(candidate_data, f, indent=2)
