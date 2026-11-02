"""Generate synthetic sensor data so the API has something to serve.

On Render's free tier the filesystem is ephemeral, so SQLite data is lost on
restart. Seeding on startup keeps the demo working; use DATABASE_URL (Postgres)
for data that must persist.
"""
import random
from datetime import datetime, timedelta, timezone

from .extensions import db
from .models import Device, Reading

DEVICES = [
    ("sensor-boulder-01", "Boulder"),
    ("sensor-denver-01", "Denver"),
    ("sensor-fortcollins-01", "Fort Collins"),
    ("sensor-aspen-01", "Aspen"),
    ("sensor-pueblo-01", "Pueblo"),
]


def seed_if_empty(n_readings):
    if Device.query.first() is not None:
        return
    rng = random.Random(42)
    devices = [Device(name=n, location=loc) for n, loc in DEVICES]
    db.session.add_all(devices)
    db.session.flush()

    start = datetime.now(timezone.utc) - timedelta(minutes=n_readings)
    readings = []
    for i in range(n_readings):
        dev = devices[i % len(devices)]
        readings.append(
            Reading(
                device_id=dev.id,
                ts=start + timedelta(minutes=i),
                temperature=round(rng.gauss(18, 7), 2),
                humidity=round(min(100, max(0, rng.gauss(45, 15))), 2),
            )
        )
    db.session.bulk_save_objects(readings)
    db.session.commit()
