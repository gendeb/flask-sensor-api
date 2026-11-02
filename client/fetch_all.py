"""Pull every reading from the API page by page and load it into pandas.

This is the "API as a data source" step: the output DataFrame can be saved as
Parquet and handed to Spark, or analysed directly.

Usage:
    python client/fetch_all.py http://127.0.0.1:5000
    python client/fetch_all.py https://your-app.onrender.com --out readings.parquet
"""
import argparse
import time

import pandas as pd
import requests


def fetch_all(base_url, page_size=1000, timeout=90):
    # Long timeout: a sleeping Render free-tier service takes 30-60 s to wake.
    session = requests.Session()
    rows, offset = [], 0
    while offset is not None:
        resp = session.get(
            f"{base_url}/api/v1/readings",
            params={"limit": page_size, "offset": offset},
            timeout=timeout,
        )
        resp.raise_for_status()
        payload = resp.json()
        rows.extend(payload["data"])
        offset = payload["meta"]["next_offset"]
    return pd.DataFrame(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url")
    parser.add_argument("--out", help="optional .parquet or .csv output path")
    args = parser.parse_args()

    start = time.time()
    df = fetch_all(args.base_url.rstrip("/"))
    print(f"Fetched {len(df)} rows in {time.time() - start:.1f}s")
    print(df.groupby("device_id")[["temperature", "humidity"]].mean().round(2))

    if args.out:
        df.to_parquet(args.out) if args.out.endswith(".parquet") else df.to_csv(args.out, index=False)
        print(f"Saved to {args.out}")
