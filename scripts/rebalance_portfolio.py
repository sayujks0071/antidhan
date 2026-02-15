import json
import os
import shutil
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Rebalancer")

def rebalance():
    if not os.path.exists("audit_results.json"):
        logger.error("audit_results.json not found. Run audit first.")
        return

    with open("audit_results.json", "r") as f:
        data = json.load(f)

    correlation_pairs = data.get("correlation_pairs", [])
    strategies = data.get("strategies", {})

    archive_dir = os.path.join("openalgo", "strategies", "scripts", "archive")
    if not os.path.exists(archive_dir):
        os.makedirs(archive_dir)

    strategies_dir = os.path.join("openalgo", "strategies", "scripts")

    processed_strategies = set()

    for pair in correlation_pairs:
        s1 = pair['strategy_1']
        s2 = pair['strategy_2']
        corr = pair['correlation']

        if corr <= 0.7:
            continue

        # Check if already processed (to avoid double moves if involved in multiple pairs)
        if s1 in processed_strategies or s2 in processed_strategies:
            continue

        s1_calmar = pair['s1_calmar']
        s2_calmar = pair['s2_calmar']

        if s1_calmar > s2_calmar:
            to_deprecate = s2
            keep = s1
        else:
            to_deprecate = s1
            keep = s2

        logger.info(f"Pair: {s1} vs {s2} (Corr: {corr:.2f}). Deprecating {to_deprecate} (Calmar: {min(s1_calmar, s2_calmar):.2f} vs {max(s1_calmar, s2_calmar):.2f})")

        src = os.path.join(strategies_dir, f"{to_deprecate}.py")
        dst = os.path.join(archive_dir, f"{to_deprecate}.py")

        if os.path.exists(src):
            try:
                shutil.move(src, dst)
                logger.info(f"Moved {to_deprecate}.py to archive.")
                processed_strategies.add(to_deprecate)
            except Exception as e:
                logger.error(f"Failed to move {src}: {e}")
        else:
            logger.warning(f"File {src} not found (maybe already moved).")

if __name__ == "__main__":
    rebalance()
