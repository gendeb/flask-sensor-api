from datetime import datetime, timezone

from .extensions import db

# Units of the measurement fields. Returned in API responses so consumers
# never have to guess (temperature is Celsius, humidity is relative humidity %).
UNITS = {"temperature": "C", "humidity": "%"}


class Device(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    location = db.Column(db.String(64), nullable=False)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "location": self.location}


class Reading(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey("device.id"), nullable=False, index=True)
    ts = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    temperature = db.Column(db.Float, nullable=False)
    humidity = db.Column(db.Float, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "device_id": self.device_id,
            "ts": self.ts.isoformat(),
            "temperature": self.temperature,
            "humidity": self.humidity,
        }
