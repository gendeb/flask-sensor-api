"""Forecast a value with machine learning, and test whether the models really help.

The data is averaged to one value per hour. Each model predicts the next hour
from the previous hours (lags) and the hour of day. Models are trained on the
first 80% of the timeline and scored on the last 20%, which they never saw
(a time-ordered split, never shuffled, so the future cannot leak into training).
Every model is compared with simple baselines: if a model cannot beat them, it
has learned nothing useful.

    python client/forecast.py --api https://sensor-api-wrmk.onrender.com
    python client/forecast.py --api http://127.0.0.1:5000 --where device_id=1 --steps 12
    python client/forecast.py --csv mydata.csv --value price --time date
"""
import argparse

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import sources

LAGS = (1, 2, 3, 24)  # hours back: recent trend, plus the same hour yesterday
TRAIN_FRACTION = 0.8
MIN_HOURS = max(LAGS) + 48


def hourly_series(df, time, value):
    """Average `value` per hour, filling short gaps by interpolation."""
    t = pd.to_datetime(df[time])
    s = df.assign(**{time: t}).set_index(time)[value].resample("h").mean()
    return s.interpolate(limit=3).dropna()


def _time_features(index):
    hour = np.asarray(index.hour)
    return {"hour_sin": np.sin(2 * np.pi * hour / 24), "hour_cos": np.cos(2 * np.pi * hour / 24)}


def build_features(series, lags=LAGS):
    """Feature table (lags + hour of day) and target for one-step-ahead prediction."""
    X = pd.DataFrame({f"lag_{k}": series.shift(k) for k in lags}, index=series.index)
    for name, col in _time_features(series.index).items():
        X[name] = col
    X = X.dropna()
    return X, series.loc[X.index]


def time_split(X, y, train_fraction=TRAIN_FRACTION):
    """First part of the timeline for training, the last part for testing."""
    cut = int(len(X) * train_fraction)
    return X.iloc[:cut], X.iloc[cut:], y.iloc[:cut], y.iloc[cut:]


def make_models():
    return {
        "Ridge regression": make_pipeline(StandardScaler(), Ridge(alpha=1.0)),
        "Gradient boosting": GradientBoostingRegressor(random_state=0),
    }


def score(y_true, y_pred):
    return {
        "MAE": float(mean_absolute_error(y_true, y_pred)),
        "RMSE": float(np.sqrt(mean_squared_error(y_true, y_pred))),
    }


def evaluate(series):
    """Train on the first 80%, score on the last 20%. Returns a table sorted by MAE."""
    X, y = build_features(series)
    X_train, X_test, y_train, y_test = time_split(X, y)

    results = {
        "Baseline: training mean": score(y_test, np.full(len(y_test), y_train.mean())),
        "Baseline: same as last hour": score(y_test, X_test["lag_1"]),
        "Baseline: same hour yesterday": score(y_test, X_test["lag_24"]),
    }
    fitted = {}
    for name, model in make_models().items():
        model.fit(X_train, y_train)
        fitted[name] = model
        results[name] = score(y_test, model.predict(X_test))

    table = pd.DataFrame(results).T.sort_values("MAE")
    return table, fitted, {"train": len(X_train), "test": len(X_test)}


def forecast_ahead(series, model, steps=24, lags=LAGS):
    """Predict the next `steps` hours, feeding each prediction back in as a lag."""
    history = series.copy()
    out = {}
    for _ in range(steps):
        ts = history.index[-1] + pd.Timedelta(hours=1)
        row = {f"lag_{k}": history.iloc[-k] for k in lags}
        row.update({name: col[0] for name, col in _time_features(pd.DatetimeIndex([ts])).items()})
        pred = float(model.predict(pd.DataFrame([row]))[0])
        history.loc[ts] = pred
        out[ts] = pred
    return pd.Series(out)


def run(df, value, time, steps=24):
    if value not in df.columns or time not in df.columns:
        raise SystemExit(f"Need columns '{value}' and '{time}'. Available columns: {list(df.columns)}")
    series = hourly_series(df, time, value)
    if len(series) < MIN_HOURS:
        raise SystemExit(f"Need at least {MIN_HOURS} hourly values to forecast, found {len(series)}.")

    table, fitted, sizes = evaluate(series)
    print(f"Series: {len(series)} hourly averages of '{value}' ({series.index[0]} to {series.index[-1]})")
    print(f"Trained on {sizes['train']} hours, tested on the last {sizes['test']} hours (unseen)\n")
    print("== Test error (lower is better; same units as the data) ==")
    print(table.round(3), "\n")

    models_only = table.loc[[n for n in table.index if n in fitted]]
    baselines = table.loc[[n for n in table.index if n.startswith("Baseline")]]
    best_name = models_only["MAE"].idxmin()
    best_baseline = baselines["MAE"].idxmin()
    gain = 1 - models_only.loc[best_name, "MAE"] / baselines.loc[best_baseline, "MAE"]
    print(f"Best model: {best_name} (MAE {models_only.loc[best_name, 'MAE']:.3f})")
    print(f"Best baseline: {best_baseline} (MAE {baselines.loc[best_baseline, 'MAE']:.3f})")
    if gain > 0:
        print(f"The model's error is {gain:.1%} lower than the best baseline.\n")
    else:
        print(f"The model is {-gain:.1%} WORSE than the best baseline: it has not learned anything useful here.\n")

    # Refit the best model on all data before forecasting the future.
    X, y = build_features(series)
    final = make_models()[best_name].fit(X, y)
    future = forecast_ahead(series, final, steps)
    print(f"== Forecast for the next {steps} hours ==")
    print(future.round(2).to_string())


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sources.add_source_args(p)
    p.add_argument("--value", default="temperature", help="numeric column to forecast (default: temperature)")
    p.add_argument("--time", default="ts", help="timestamp column (default: ts)")
    p.add_argument("--where", metavar="COL=VALUE", help="keep only rows where COL equals VALUE, e.g. device_id=1")
    p.add_argument("--steps", type=int, default=24, help="hours to forecast (default: 24)")
    args = p.parse_args()

    df = sources.load_from_args(args)
    if args.where:
        col, _, val = args.where.partition("=")
        if col not in df.columns:
            raise SystemExit(f"Column '{col}' not found. Available columns: {list(df.columns)}")
        df = df[df[col].astype(str) == val]
    run(df, args.value, args.time, args.steps)


if __name__ == "__main__":
    main()
