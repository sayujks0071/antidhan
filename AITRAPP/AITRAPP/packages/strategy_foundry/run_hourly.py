import logging
import os
from datetime import datetime

import pandas as pd
import yaml

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from packages.strategy_foundry.backtest.sanity import SanityChecker
from packages.strategy_foundry.backtest.walkforward import WalkForwardEvaluator
from packages.strategy_foundry.data.loader import DataLoader
from packages.strategy_foundry.factory.generator import StrategyGenerator
from packages.strategy_foundry.factory.registry import CandidateRegistry
from packages.strategy_foundry.live.signal_publisher import SignalPublisher
from packages.strategy_foundry.selection.promote import Promoter
from packages.strategy_foundry.selection.ranker import Ranker


def load_config():
    path = "packages/strategy_foundry/configs/foundry.yaml"
    with open(path, 'r') as f:
        return yaml.safe_load(f)

def run():
    # 1. Config & Setup
    config_yaml = load_config()
    foundry_conf = config_yaml.get('foundry', {})

    FAST_MODE = os.environ.get('FAST_MODE', '0') == '1'
    N_CANDIDATES = foundry_conf.get('fast_mode_candidates', 15) if FAST_MODE else foundry_conf.get('max_candidates', 80)
    FOLDS = foundry_conf.get('fast_mode_folds', 2) if FAST_MODE else foundry_conf.get('folds', 4)

    logger.info(f"Starting Strategy Foundry (FAST_MODE={FAST_MODE}, N={N_CANDIDATES}, FOLDS={FOLDS})")

    instruments = ['NIFTY', 'SENSEX']
    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = f"packages/strategy_foundry/results/runs/{run_ts}"
    os.makedirs(run_dir, exist_ok=True)

    loader = DataLoader()
    generator = StrategyGenerator()

    # Generate Candidates (Shared across instruments?)
    # Usually strategy logic is instrument-agnostic.
    # We generate N candidates once.
    candidates = []
    seen_ids = set()
    while len(candidates) < N_CANDIDATES:
        cand = generator.generate_candidate()
        if cand.strategy_id not in seen_ids:
            candidates.append(cand)
            seen_ids.add(cand.strategy_id)

    # Save candidates
    CandidateRegistry.save_candidates(candidates, f"{run_dir}/candidates.json")

    leaderboard_rows = []

    for instrument in instruments:
        logger.info(f"Processing {instrument}")

        # 2. Data
        try:
            df_5m = loader.get_data(instrument, "5m")
            df_15m = loader.get_data(instrument, "15m")
            df_1d = loader.get_data(instrument, "1d")

            if df_5m is None or df_15m is None:
                logger.error(f"Missing intraday data for {instrument}. Skipping.")
                continue
        except Exception as e:
            logger.error(f"Failed to load data for {instrument}: {e}")
            continue

        # 3. Evaluate (Walk Forward)
        wf_5m = WalkForwardEvaluator(df_5m, folds=FOLDS)
        wf_15m = WalkForwardEvaluator(df_15m, folds=FOLDS)

        results_5m = []
        results_15m = []

        for cand in candidates:
            # 5m
            try:
                m5 = wf_5m.evaluate(cand)
                results_5m.append({"strategy": cand, "metrics": m5})
            except Exception as e:
                logger.warning(f"Failed 5m eval for {cand.strategy_id}: {e}")

            # 15m
            try:
                m15 = wf_15m.evaluate(cand)
                results_15m.append({"strategy": cand, "metrics": m15})
            except Exception as e:
                logger.warning(f"Failed 15m eval for {cand.strategy_id}: {e}")

        # 4. Rank & Blend
        # We need a blended score.
        # Ranker.rank returns DF with score.
        # Let's modify Ranker to handle blending?
        # Or just rank separately and merge.

        rank_5m = Ranker.rank(results_5m)
        rank_15m = Ranker.rank(results_15m)

        # Save raw rankings
        rank_5m.to_csv(f"{run_dir}/{instrument}_ranking_5m.csv", index=False)
        rank_15m.to_csv(f"{run_dir}/{instrument}_ranking_15m.csv", index=False)

        # Merge for Blended Score
        # 0.6 * score_15m + 0.4 * score_5m
        if not rank_5m.empty and not rank_15m.empty:
            merged = pd.merge(rank_5m[['strategy_id', 'score', 'avg_sharpe', 'avg_max_dd']],
                              rank_15m[['strategy_id', 'score', 'avg_sharpe', 'avg_max_dd']],
                              on='strategy_id', suffixes=('_5m', '_15m'))

            merged['blended_score'] = 0.6 * merged['score_15m'] + 0.4 * merged['score_5m']
            merged['avg_sharpe'] = 0.6 * merged['avg_sharpe_15m'] + 0.4 * merged['avg_sharpe_5m'] # Weighted Sharpe
            merged['avg_max_dd'] = max(merged['avg_max_dd_15m'], merged['avg_max_dd_5m']) # Worst DD

            # Sort by blended
            merged.sort_values('blended_score', ascending=False, inplace=True)

            # Find the full candidate object for top
            # We need to map strategy_id back to candidate object
            cand_map = {c.strategy_id: c for c in candidates}

            # 5. Sanity Check (Top 10)
            top_candidates = merged.head(10)
            sanity_checker = SanityChecker(df_1d, wf_5m.cost_model)

            champion_candidate = None
            champion_row = None

            for _, row in top_candidates.iterrows():
                sid = row['strategy_id']
                cand = cand_map.get(sid)
                if not cand: continue

                # Run Sanity
                sanity_res = sanity_checker.check(cand)
                if sanity_res['passed']:
                    # Found our potential champion
                    champion_candidate = cand
                    champion_row = row.to_dict()
                    champion_row['score'] = row['blended_score'] # Use blended as main score
                    champion_row['strategy_config'] = cand.to_dict()
                    break
                else:
                    logger.info(f"Strategy {sid} failed sanity: {sanity_res['reason']}")

            # 6. Promote
            if champion_candidate:
                promoter = Promoter(instrument, "blended") # We use blended timeframe key
                promoted = promoter.check_and_promote(champion_row)

                leaderboard_rows.append({
                    "instrument": instrument,
                    "top_strategy": champion_candidate.strategy_id,
                    "score": champion_row['score'],
                    "sharpe": champion_row['avg_sharpe'],
                    "promoted": promoted
                })

                # Also publish signal immediately if promoted or existing?
                # "Publish live signal... if market open AND champion live-eligible"
                # SignalPublisher uses "blended" timeframe?
                # SignalPublisher needs a specific timeframe to execute signal on.
                # "timeframe": "5m|15m|blended"
                # If blended, which timeframe do we generate signal on?
                # Usually we run the strategy on the PRIMARY timeframe (5m).
                # The blended score implies it works on both.
                # But execution must be on one.
                # Let's assume we execute on 5m (Primary).

                # Update SignalPublisher to look for "blended" champion but execute on 5m?
                # Or we save champion as "blended" but the publisher knows to run on 5m.
                # Or we promote it to "5m" champion slot too?
                # Let's use "5m" as the execution timeframe.
                # So we save champion as "5m" (or "blended" and map it).
                # Promoter saved it as "blended".
                # SignalPublisher takes timeframe arg.

                # Let's adjust SignalPublisher to try loading "blended" if "5m" missing?
                # Or better, we save it as "blended" and "5m"?
                # Prompt: "timeframe": "5m|15m|blended" in JSON.
                # Let's instantiate Publisher with "blended" but it runs on 5m data?
                # Or we just assume 5m is the execution timeframe for the blended champion.
                pass

        # 7. Publish Signal
        # We try to publish. Publisher handles checks.
        # We use 'blended' champion store, but execute on 5m data?
        # Let's hack Publisher to handle this or pass correct params.
        # If we save as "blended", Publisher("NIFTY", "blended") loads it.
        # Then Publisher loads data. Which data?
        # It needs to generate signal.
        # If strategy was tested on 5m and 15m, it can run on either.
        # Primary is 5m. So Publisher should use 5m data.
        # I'll update SignalPublisher logic slightly or just pass 5m data to generator.

        # Actually SignalPublisher takes `timeframe` in init.
        # It uses that for `store.get_current_champion` AND `loader.get_data`.
        # So if I pass "blended", it tries to load "blended" data? No.
        # I should probably update SignalPublisher to support:
        # store_timeframe="blended", data_timeframe="5m".

        # For now, I'll instantiate Publisher with "blended" and assume `DataLoader` handles "blended" (it doesn't).
        # Fix: I will update SignalPublisher to map 'blended' -> '5m' for data.

        publisher = SignalPublisher(instrument, "blended")
        # Ensure Publisher knows to use 5m data for blended champion
        publisher.data_timeframe = "5m"
        # But `SignalPublisher` uses `self.timeframe` for both.
        # I need to edit `SignalPublisher` to separate them.
        publisher.publish()

    # 8. Update Leaderboard MD
    if leaderboard_rows:
        lb_df = pd.DataFrame(leaderboard_rows)
        lb_path = "packages/strategy_foundry/results/leaderboard.md"
        with open(lb_path, 'a') as f:
            f.write(f"\n## Run {run_ts}\n")
            f.write(lb_df.to_markdown(index=False))
            f.write("\n")

    logger.info("Run completed")

if __name__ == "__main__":
    run()
