from flask import Blueprint, current_app, jsonify, request

from ..extensions import db
from ..models import UNITS, Device, Reading

bp = Blueprint("readings", __name__)


@bp.get("")
def list_readings():
    """Paginated, filterable list. Small pages keep responses fast and bounded."""
    cfg = current_app.config
    limit = request.args.get("limit", cfg["DEFAULT_PAGE_SIZE"], type=int)
    offset = request.args.get("offset", 0, type=int)
    device_id = request.args.get("device_id", type=int)

    if limit is None or limit < 1 or offset is None or offset < 0:
        return jsonify(error="limit must be >= 1 and offset >= 0"), 400
    limit = min(limit, cfg["MAX_PAGE_SIZE"])

    query = Reading.query
    if device_id is not None:
        query = query.filter_by(device_id=device_id)

    total = query.count()
    rows = query.order_by(Reading.id).offset(offset).limit(limit).all()

    next_offset = offset + limit
    return jsonify(
        data=[r.to_dict() for r in rows],
        meta={
            "total": total,
            "limit": limit,
            "offset": offset,
            "next_offset": next_offset if next_offset < total else None,
            "units": UNITS,
        },
    )


@bp.get("/<int:reading_id>")
def get_reading(reading_id):
    return jsonify(**db.get_or_404(Reading, reading_id).to_dict(), units=UNITS)


@bp.post("")
def create_reading():
    body = request.get_json(silent=True) or {}
    missing = [k for k in ("device_id", "temperature", "humidity") if k not in body]
    if missing:
        return jsonify(error=f"missing fields: {', '.join(missing)}"), 400

    try:
        temperature = float(body["temperature"])
        humidity = float(body["humidity"])
    except (TypeError, ValueError):
        return jsonify(error="temperature and humidity must be numbers"), 400
    if not 0 <= humidity <= 100:
        return jsonify(error="humidity must be between 0 and 100 (%)"), 400
    if db.session.get(Device, body["device_id"]) is None:
        return jsonify(error="unknown device_id"), 404

    reading = Reading(device_id=body["device_id"], temperature=temperature, humidity=humidity)
    db.session.add(reading)
    db.session.commit()
    return jsonify(**reading.to_dict(), units=UNITS), 201
