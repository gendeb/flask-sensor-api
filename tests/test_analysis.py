import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "client"))
import analyze  # noqa: E402


@pytest.fixture()
def cyclic():
    """Four days of hourly data: a clear daily cycle plus a rising trend."""
    ts = pd.date_range("2026-01-01", periods=96, freq="h")
    hour = ts.hour.to_numpy()
    value = 10 + 5 * np.sin(2 * np.pi * hour / 24) + np.arange(96) * 0.1
    return pd.DataFrame({"ts": ts, "temperature": value, "device_id": [1, 2] * 48})


def test_summarize_overall_and_grouped(cyclic):
    assert analyze.summarize(cyclic, "temperature").loc[:, "count"].iloc[0] == 96
    assert len(analyze.summarize(cyclic, "temperature", "device_id")) == 2


def test_daily_pattern_detected(cyclic):
    dp = analyze.daily_pattern(cyclic, "ts", "temperature")
    assert dp["has_pattern"]
    assert dp["peak_hour"] in (5, 6, 7)


def test_no_daily_pattern_in_noise():
    rng = np.random.default_rng(0)
    ts = pd.date_range("2026-01-01", periods=2000, freq="min")
    df = pd.DataFrame({"ts": ts, "v": rng.normal(0, 1, 2000)})
    assert not analyze.daily_pattern(df, "ts", "v")["has_pattern"]


def test_trend_slope():
    # value rises exactly 0.1 per hour = 2.4 per day
    ts = pd.date_range("2026-01-01", periods=96, freq="h")
    df = pd.DataFrame({"ts": ts, "v": np.arange(96) * 0.1})
    tr = analyze.trend(df, "ts", "v")
    assert tr["slope_per_day"] == pytest.approx(2.4, abs=0.01)
    assert tr["r"] == pytest.approx(1.0)


def test_anomalies_found():
    df = pd.DataFrame({"v": [10.0] * 99 + [500.0]})
    out = analyze.anomalies(df, "v")
    assert len(out) == 1 and out["v"].iloc[0] == 500.0


def test_correlation():
    df = pd.DataFrame({"a": [1, 2, 3, 4], "b": [2, 4, 6, 8]})
    assert analyze.correlation(df, "a", "b") == 1.0


def test_run_rejects_missing_column(cyclic):
    with pytest.raises(SystemExit):
        analyze.run(cyclic, "nope")
