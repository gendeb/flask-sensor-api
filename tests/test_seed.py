"""The seeded data should look like real sensor data, not random numbers."""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "client"))
import analyze  # noqa: E402

from app import create_app  # noqa: E402
from app.config import TestConfig  # noqa: E402
from app.models import Device, Reading  # noqa: E402


class ThreeDays(TestConfig):
    SEED_READINGS = 3 * 24 * 60


@pytest.fixture(scope="module")
def df():
    app = create_app(ThreeDays)
    with app.app_context():
        rows = [r.to_dict() for r in Reading.query.all()]
        names = {d.id: d.location for d in Device.query.all()}
    out = pd.DataFrame(rows)
    out["location"] = out["device_id"].map(names)
    return out


def test_readings_are_seeded(df):
    assert len(df) == ThreeDays.SEED_READINGS
    assert df["location"].nunique() == 5


def test_temperature_has_a_daily_cycle(df):
    dp = analyze.daily_pattern(df, "ts", "temperature")
    assert dp["has_pattern"]
    assert dp["variance_explained"] > 0.3
    assert 18 <= dp["peak_hour"] <= 23  # warmest in the afternoon (UTC)


def test_humidity_falls_as_temperature_rises(df):
    assert analyze.correlation(df, "temperature", "humidity") < -0.5


def test_climates_differ_by_location(df):
    means = df.groupby("location")["temperature"].mean()
    assert means["Aspen"] < means["Boulder"] < means["Pueblo"]


def test_values_are_in_valid_ranges(df):
    assert df["humidity"].between(0, 100).all()
    assert df["temperature"].between(-30, 50).all()
