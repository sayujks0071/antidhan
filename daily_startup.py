#!/usr/bin/env python3
import os
import sys
import subprocess
import shutil

REPO_URL = "https://github.com/dheerajw7/OpenAlgo.git" # Placeholder/Best Guess
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
        print(f"Directory '{TARGET_DIR}' exists. Verifying it's a valid repo...")
        # Optional: Check if it's a git repo
        if not os.path.exists(os.path.join(TARGET_DIR, ".git")):
            print("Warning: Directory exists but does not appear to be a git repository.")

def run_daily_prep():
    prep_script = os.path.join(TARGET_DIR, "scripts", "daily_prep.py")
    if not os.path.exists(prep_script):
        # Fallback: maybe it's in openalgo/openalgo/scripts if cloned? No, standard structure.
        # Check if I need to use openalgo/scripts/daily_prep.py relative to root
        prep_script = os.path.join(TARGET_DIR, "openalgo", "scripts", "daily_prep.py")
        if not os.path.exists(prep_script):
             prep_script = os.path.join(TARGET_DIR, "scripts", "daily_prep.py") # Try first one again

    # Actually, in this env, 'openalgo/scripts/daily_prep.py' is where I put it.
    prep_script = os.path.join("openalgo", "scripts", "daily_prep.py")

    if not os.path.exists(prep_script):
        print(f"Error: {prep_script} not found.")
        sys.exit(1)

    print(f"Executing {prep_script}...")
    try:
        # Pass current environment + PYTHONPATH
        env = os.environ.copy()
        env['PYTHONPATH'] = os.getcwd() + ":" + env.get('PYTHONPATH', '')

        # We need to run it with the venv python if available
        venv_python = os.path.join("openalgo", "venv", "bin", "python3")
        python_exec = venv_python if os.path.exists(venv_python) else sys.executable

        subprocess.check_call([python_exec, prep_script], env=env)
    except subprocess.CalledProcessError as e:
        print(f"Daily Prep failed with exit code {e.returncode}")
        sys.exit(e.returncode)

def main():
    print("=== DAILY STARTUP ROUTINE ===")
    check_and_clone()
    run_daily_prep()

if __name__ == "__main__":
    main()
