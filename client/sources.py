"""Step 1: load data from a source of your choice into a pandas DataFrame.

Supported sources:
    api  - this project's REST API (paginated, via fetch_all)
    csv  - a local CSV file
    url  - a CSV or JSON file on the web
"""
import pandas as pd

from fetch_all import fetch_all


def load_api(base_url):
    return fetch_all(base_url.rstrip("/"))


def load_csv(path):
    return pd.read_csv(path)


def load_url(url):
    # Records-oriented JSON or CSV; chosen by file extension, CSV by default.
    if url.lower().split("?")[0].endswith(".json"):
        return pd.read_json(url)
    return pd.read_csv(url)


def add_source_args(parser):
    """Add the --api / --csv / --url options shared by the analysis scripts."""
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--api", metavar="BASE_URL", help="this project's API, e.g. https://sensor-api-wrmk.onrender.com")
    src.add_argument("--csv", metavar="PATH", help="a local CSV file")
    src.add_argument("--url", metavar="URL", help="a CSV or JSON file on the web")


def load_from_args(args):
    if args.api:
        return load_api(args.api)
    if args.csv:
        return load_csv(args.csv)
    return load_url(args.url)
