#!/usr/bin/env python3
import os
import sys
import subprocess
import argparse

REPO_URL = "https://github.com/dheerajw7/OpenAlgo.git"
TARGET_DIR = "openalgo"

def check_and_clone():
    if not os.path.exists(TARGET_DIR):
        print(f"Directory '{TARGET_DIR}' not found. Cloning from {REPO_URL}...")
        try:
            subprocess.check_call(["git", "clone", REPO_URL, TARGET_DIR])
            print("Cloning successful.")
        except subprocess.CalledProcessError as e:
            print(f"Failed to clone repository: {e}")
            sys.exit(1)
    else:
        print(f"Directory '{TARGET_DIR}' exists.")

def run_script(script_path, description):
    if not os.path.exists(script_path):
        print(f"Error: {script_path} not found.")
        sys.exit(1)

    print(f"Executing {description} ({script_path})...")
    try:
        env = os.environ.copy()
        env['PYTHONPATH'] = os.getcwd() + ":" + env.get('PYTHONPATH', '')

        # Use venv if exists, else system python
        venv_python = os.path.join("openalgo", "venv", "bin", "python3")
        python_exec = venv_python if os.path.exists(venv_python) else sys.executable

        subprocess.check_call([python_exec, script_path], env=env)
        print(f"✅ {description} Success.")
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} Failed with exit code {e.returncode}")
        sys.exit(e.returncode)

def main():
    parser = argparse.ArgumentParser(description="OpenAlgo Daily Startup Routine")
    parser.add_argument("--backtest", action="store_true", help="Run backtest and leaderboard generation after prep")
    args = parser.parse_args()

    print("=== DAILY STARTUP ROUTINE ===")

    # 1. Ensure Repo
    check_and_clone()

    # 2. Daily Prep
    prep_script = os.path.join("openalgo", "scripts", "daily_prep.py")
    run_script(prep_script, "Daily Prep")

    # 3. Backtest (Optional)
    if args.backtest:
        backtest_script = os.path.join("openalgo", "scripts", "daily_backtest_leaderboard.py")
        run_script(backtest_script, "Daily Backtest & Leaderboard")

    print("=== DAILY ROUTINE COMPLETE ===")

if __name__ == "__main__":
    main()
