import os
import logging
import sys
import shutil

# Ensure repo root is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from openalgo_observability.logging_setup import setup_logging

def test_logging():
    print("Testing logging setup...")

    # Clean up old logs for test
    if os.path.exists("logs/openalgo.log"):
        os.remove("logs/openalgo.log")

    setup_logging()

    logger = logging.getLogger("test_logger")

    # Test secret redaction
    secret = "my_super_secret_api_key_12345"
    logger.info(f"Connecting with api_key={secret}")
    logger.info("Normal message")

    # Check if file exists
    if os.path.exists("logs/openalgo.log"):
        print("Log file created.")
        with open("logs/openalgo.log", "r") as f:
            content = f.read()
            if "api_key=[REDACTED]" in content:
                print("SUCCESS: Secret redacted in file.")
            else:
                print("FAILURE: Secret NOT redacted in file.")
                print("Content preview:", content[-200:])

            if "Normal message" in content:
                print("SUCCESS: Normal message found.")
            else:
                 print("FAILURE: Normal message NOT found.")
    else:
        print("FAILURE: Log file not found.")

if __name__ == "__main__":
    test_logging()
