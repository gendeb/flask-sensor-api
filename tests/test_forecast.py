import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "client"))
import forecast  # noqa: E402

MEAN = "Baseline: training mean"
PERSIST = "Baseline: same as last hour"


def cyclic_series(days=14, noise=0.5, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-01-01", periods=days * 24, freq="h")
    values = 15 + 7 * np.cos(2 * np.pi * (np.asarray(idx.hour) - 15) / 24) + rng.normal(0, noise, len(idx))
    return pd.Series(values, index=idx)


def test_features_have_no_gaps_and_match_target():
    X, y = forecast.build_features(cyclic_series())
    assert not X.isna().any().any()
    assert list(X.index) == list(y.index)
    assert {"lag_1", "lag_24", "hour_sin", "hour_cos"} <= set(X.columns)


def test_lag_feature_is_the_previous_value():
    s = cyclic_series()
    X, _ = forecast.build_features(s)
    t = X.index[10]
    assert X.loc[t, "lag_1"] == s.shift(1).loc[t]
    assert X.loc[t, "lag_24"] == s.shift(24).loc[t]


def test_time_split_is_ordered_with_no_overlap():
    X, y = forecast.build_features(cyclic_series())
    X_train, X_test, y_train, y_test = forecast.time_split(X, y)
    assert X_train.index.max() < X_test.index.min()
    assert len(X_train) + len(X_test) == len(X)
    assert abs(len(X_train) / len(X) - 0.8) < 0.01


def test_models_beat_baselines_on_cyclic_data():
    table, fitted, _ = forecast.evaluate(cyclic_series())
    best_model = min(table.loc[n, "MAE"] for n in fitted)
    assert best_model < 0.3 * table.loc[MEAN, "MAE"]
    assert best_model < table.loc[PERSIST, "MAE"]


def test_models_do_not_beat_mean_on_pure_noise():
    rng = np.random.default_rng(1)
    idx = pd.date_range("2026-01-01", periods=14 * 24, freq="h")
    noise = pd.Series(rng.normal(0, 1, len(idx)), index=idx)
    table, fitted, _ = forecast.evaluate(noise)
    best_model = min(table.loc[n, "MAE"] for n in fitted)
    assert best_model > 0.9 * table.loc[MEAN, "MAE"]


def test_forecast_ahead_continues_the_timeline_and_the_cycle():
    s = cyclic_series()
    X, y = forecast.build_features(s)
    model = forecast.make_models()["Ridge regression"].fit(X, y)
    out = forecast.forecast_ahead(s, model, steps=24)
    assert len(out) == 24
    assert out.index[0] == s.index[-1] + pd.Timedelta(hours=1)
    assert out.max() - out.min() > 8  # the predicted day still swings (true swing is 14)


def test_hourly_series_averages_per_hour():
    ts = pd.date_range("2026-01-01", periods=120, freq="min")
    df = pd.DataFrame({"ts": ts, "v": np.arange(120.0)})
    s = forecast.hourly_series(df, "ts", "v")
    assert len(s) == 2 and s.iloc[0] == pytest.approx(29.5)


def test_run_requires_enough_data_and_valid_columns():
    short = pd.DataFrame({"ts": pd.date_range("2026-01-01", periods=48, freq="h"), "v": range(48)})
    with pytest.raises(SystemExit):
        forecast.run(short, "v", "ts")
    with pytest.raises(SystemExit):
        forecast.run(short, "missing", "ts")
