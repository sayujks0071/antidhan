"""AITRAPP integration module for backtesting"""
import os
import sys
from pathlib import Path

# Add AITRAPP to Python path
def setup_aitrapp_path():
    """Add AITRAPP repository to Python path"""
    # Try to find AITRAPP repository
    # Check common locations
    possible_paths = [
        Path(__file__).resolve().parent.parent.parent.parent / "AITRAPP" / "AITRAPP",
        Path(__file__).resolve().parent.parent.parent.parent.parent / "AITRAPP" / "AITRAPP",
    ]
    
    aitrapp_path = None
    for path in possible_paths:
        if path.exists() and (path / "packages").exists():
            aitrapp_path = path
            break
    
    if not aitrapp_path:
        # Try to find it relative to current file
        current = Path(__file__).resolve()
        # Go up from utils -> strategies -> openalgo -> dyad-apps
        base = current.parent.parent.parent.parent
        aitrapp_path = base / "AITRAPP" / "AITRAPP"
        if not aitrapp_path.exists():
            raise FileNotFoundError(
                f"AITRAPP repository not found. Tried: {possible_paths}\n"
                f"Please ensure AITRAPP/AITRAPP directory exists."
            )
    
    if str(aitrapp_path) not in sys.path:
        sys.path.insert(0, str(aitrapp_path))
    
    return aitrapp_path


# Setup path on import
AITRAPP_PATH = setup_aitrapp_path()

# Change to AITRAPP directory for config loading
import os
_original_cwd = os.getcwd()
try:
    os.chdir(str(AITRAPP_PATH))
except:
    pass

# Import AITRAPP modules
try:
    from packages.core.backtest import BacktestEngine
    from packages.core.historical_data import HistoricalDataLoader
    from packages.core.strategies.base import Strategy, StrategyContext
    from packages.core.models import Signal, SignalSide, Instrument, InstrumentType, Bar, Tick
finally:
    # Restore original directory
    try:
        os.chdir(_original_cwd)
    except:
        pass

__all__ = [
    "AITRAPP_PATH",
    "BacktestEngine",
    "HistoricalDataLoader",
    "Strategy",
    "StrategyContext",
    "Signal",
    "SignalSide",
    "Instrument",
    "InstrumentType",
    "Bar",
    "Tick",
]
