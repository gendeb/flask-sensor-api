"""Generate synthetic but realistic sensor data so the API has something to serve.

Temperature (Celsius) = device climate baseline
                      + daily cycle (warmest mid-afternoon, coolest before dawn)
                      + slowly drifting "weather" shared by all devices
                      + small measurement noise
Humidity (%) falls as temperature rises above normal, plus noise.

Timestamps are UTC; the daily cycle peaks at 21:00 UTC (about 3 pm in Colorado).

On Render's free tier the filesystem is ephemeral, so SQLite data is lost on
restart. Seeding on startup keeps the demo working; use DATABASE_URL (Postgres)
for data that must persist.
"""
import math
import random
from datetime import datetime, timedelta, timezone

from .extensions import db
from .models import Device, Reading

# (name, location, temperature offset from the 15 C baseline)
DEVICES = [
    ("sensor-boulder-01", "Boulder", 0.0),
    ("sensor-denver-01", "Denver", 1.0),
    ("sensor-fortcollins-01", "Fort Collins", -1.0),
    ("sensor-aspen-01", "Aspen", -6.0),
    ("sensor-pueblo-01", "Pueblo", 2.5),
]

BASE_TEMP = 15.0
DAILY_AMPLITUDE = 7.0
PEAK_HOUR_UTC = 21
DRIFT_PERSISTENCE = 0.98  # hour-to-hour memory of the weather drift
DRIFT_STEP_STD = 0.5
TEMP_NOISE_STD = 0.7
HUMIDITY_NOISE_STD = 3.0
HUMIDITY_BASE = 50.0
HUMIDITY_PER_DEGREE = 1.8  # percentage points lost per degree above normal


def seed_if_empty(n_readings):
    if Device.query.first() is not None:
        return
    rng = random.Random(42)
    devices = [Device(name=n, location=loc) for n, loc, _ in DEVICES]
    db.session.add_all(devices)
    db.session.flush()

    # One weather drift value per hour, shared by every device.
    drift = [0.0]
    for _ in range(n_readings // 60 + 1):
        drift.append(DRIFT_PERSISTENCE * drift[-1] + rng.gauss(0, DRIFT_STEP_STD))

    start = datetime.now(timezone.utc) - timedelta(minutes=n_readings)
    readings = []
    for i in range(n_readings):
        k = i % len(devices)
        ts = start + timedelta(minutes=i)
        hour = ts.hour + ts.minute / 60
        cycle = DAILY_AMPLITUDE * math.cos(2 * math.pi * (hour - PEAK_HOUR_UTC) / 24)
        deviation = cycle + drift[i // 60]
        temperature = BASE_TEMP + DEVICES[k][2] + deviation + rng.gauss(0, TEMP_NOISE_STD)
        humidity = HUMIDITY_BASE - HUMIDITY_PER_DEGREE * deviation + rng.gauss(0, HUMIDITY_NOISE_STD)
        readings.append(
            Reading(
                device_id=devices[k].id,
                ts=ts,
                temperature=round(temperature, 2),
                humidity=round(min(100.0, max(0.0, humidity)), 2),
            )
        )
    db.session.bulk_save_objects(readings)
    db.session.commit()
