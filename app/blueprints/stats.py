from flask import Blueprint, jsonify, request
from sqlalchemy import func

from ..extensions import cache, db
from ..models import UNITS, Reading

bp = Blueprint("stats", __name__)


@bp.get("/summary")
@cache.cached(query_string=True)  # repeated aggregate queries never hit the DB within the timeout
def summary():
    device_id = request.args.get("device_id", type=int)
    query = db.session.query(
        func.count(Reading.id),
        func.avg(Reading.temperature),
        func.min(Reading.temperature),
        func.max(Reading.temperature),
        func.avg(Reading.humidity),
    )
    if device_id is not None:
        query = query.filter(Reading.device_id == device_id)

    count, avg_t, min_t, max_t, avg_h = query.one()
    return jsonify(
        device_id=device_id,
        count=count,
        temperature={"avg": avg_t and round(avg_t, 2), "min": min_t, "max": max_t},
        humidity={"avg": avg_h and round(avg_h, 2)},
        units=UNITS,
    )
