import numpy as np
import pandas as pd

from packages.core.historical_data import HistoricalDataLoader


def test_pandas_future_warning_repro():
    """
    Test that calling to_pydatetime on a Series does not trigger a FutureWarning
    when using the corrected implementation (list comprehension or other means).

    The actual fix is in HistoricalDataLoader.convert_to_bars and convert_to_ticks.
    This test mocks the data flow to ensure no warning is raised.
    """

    # Create a dummy DataFrame
    dates = pd.date_range(start="2024-01-01", periods=10, freq="D")
    df = pd.DataFrame({
        "Date": dates,
        "Open": np.random.rand(10),
        "High": np.random.rand(10),
        "Low": np.random.rand(10),
        "Close": np.random.rand(10),
        "No. of contracts": np.random.randint(1, 100, 10),
        "Open Int": np.random.randint(1, 100, 10)
    })

    loader = HistoricalDataLoader()

    import warnings
    with warnings.catch_warnings(record=True) as record:
        warnings.simplefilter("always")
        # Call the method that was triggering the warning
        loader.convert_to_bars(df, "NIFTY", 10000, "CE")
        loader.convert_to_ticks(df, "NIFTY", 10000, "CE")

    # Filter for the specific warning message just in case other warnings exist
    future_warnings = [
        w for w in record
        if issubclass(w.category, FutureWarning) and
        "DatetimeProperties.to_pydatetime is deprecated" in str(w.message)
    ]

    assert len(future_warnings) == 0, "FutureWarning about to_pydatetime was raised!"

if __name__ == "__main__":
    # Allow running directly
    try:
        test_pandas_future_warning_repro()
        print("Test PASSED: No FutureWarning raised.")
    except AssertionError as e:
        print(f"Test FAILED: {e}")
    except Exception as e:
        print(f"Test ERROR: {e}")
