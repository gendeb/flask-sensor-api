"""Step 2: analyse the data loaded in step 1.

Choose a source, then pick which column to analyse:

    python client/analyze.py --api https://sensor-api-wrmk.onrender.com
    python client/analyze.py --csv mydata.csv --value price --time date --group city
    python client/analyze.py --url https://example.com/data.csv --value sales

Columns: --value is the numeric column to analyse, --time an optional
timestamp column, --group an optional category column, --other an optional
second numeric column to correlate with --value. Analyses that need a column
you don't have are skipped.
"""
import argparse

import numpy as np
import pandas as pd

import sources

# Share of variance the hour of day must explain before we call it a daily pattern.
DAILY_PATTERN_THRESHOLD = 0.05


def summarize(df, value, group=None):
    """Mean, median, std, min, max and count of `value`, overall or per group."""
    agg = ["count", "mean", "median", "std", "min", "max"]
    if group and group in df.columns:
        return df.groupby(group)[value].agg(agg).round(2)
    return df[value].agg(agg).round(2).to_frame().T


def daily_pattern(df, time, value):
    """Average of `value` by hour of day, and how much of the variation hour explains."""
    hours = pd.to_datetime(df[time]).dt.hour
    by_hour = df.groupby(hours)[value].mean()
    total_var = df[value].var()
    explained = by_hour.var() / total_var if total_var else 0.0
    return {
        "by_hour": by_hour.round(2),
        "peak_hour": int(by_hour.idxmax()),
        "low_hour": int(by_hour.idxmin()),
        "variance_explained": round(float(explained), 4),
        "has_pattern": bool(explained > DAILY_PATTERN_THRESHOLD),
    }


def trend(df, time, value):
    """Linear trend of `value` over time: slope per day and correlation with time."""
    t = pd.to_datetime(df[time])
    days = (t - t.min()).dt.total_seconds() / 86400
    slope, _ = np.polyfit(days, df[value], 1)
    r = np.corrcoef(days, df[value])[0, 1]
    return {"slope_per_day": round(float(slope), 4), "r": round(float(r), 4)}


def anomalies(df, value, z=3.0):
    """Rows whose `value` is more than `z` standard deviations from the mean."""
    scores = (df[value] - df[value].mean()) / df[value].std()
    return df[scores.abs() > z]


def correlation(df, value, other):
    return round(float(df[value].corr(df[other])), 4)


def run(df, value, time=None, group=None, other=None):
    if value not in df.columns:
        raise SystemExit(f"Column '{value}' not found. Available columns: {list(df.columns)}")
    df = df.dropna(subset=[value])
    print(f"Loaded {len(df)} rows, columns: {list(df.columns)}\n")

    print(f"== Summary of '{value}'" + (f" by '{group}'" if group in df.columns else "") + " ==")
    print(summarize(df, value, group), "\n")

    if time and time in df.columns:
        dp = daily_pattern(df, time, value)
        print(f"== Daily pattern of '{value}' (mean by hour of day) ==")
        print(f"Peak hour: {dp['peak_hour']}:00   Lowest hour: {dp['low_hour']}:00")
        print(f"Hour of day explains {dp['variance_explained']:.2%} of the variation")
        print("Result:", "daily pattern detected" if dp["has_pattern"] else "no meaningful daily pattern", "\n")

        tr = trend(df, time, value)
        print(f"== Trend over time ==\nSlope: {tr['slope_per_day']} per day (r = {tr['r']})\n")
    else:
        print("(no usable --time column: skipping daily pattern and trend)\n")

    out = anomalies(df, value)
    print(f"== Anomalies (|z| > 3) ==\n{len(out)} of {len(df)} rows ({len(out) / len(df):.2%})")
    if len(out):
        print(out.head(5).to_string(index=False))
    print()

    if other and other in df.columns:
        print(f"== Correlation ==\n'{value}' vs '{other}': r = {correlation(df, value, other)}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sources.add_source_args(p)
    p.add_argument("--value", default="temperature", help="numeric column to analyse (default: temperature)")
    p.add_argument("--time", default="ts", help="timestamp column (default: ts)")
    p.add_argument("--group", default="device_id", help="category column (default: device_id)")
    p.add_argument("--other", default="humidity", help="second numeric column to correlate (default: humidity)")
    args = p.parse_args()

    run(sources.load_from_args(args), args.value, args.time, args.group, args.other)


if __name__ == "__main__":
    main()
