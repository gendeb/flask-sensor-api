from flask import Blueprint, jsonify

bp = Blueprint("health", __name__)


@bp.get("/")
def index():
    return jsonify(
        service="sensor-api",
        version="v1",
        endpoints=[
            "GET /health",
            "GET /api/v1/devices",
            "GET /api/v1/devices/<id>",
            "GET /api/v1/readings?device_id=&limit=&offset=",
            "GET /api/v1/readings/<id>",
            "POST /api/v1/readings",
            "GET /api/v1/stats/summary?device_id=",
        ],
    )


@bp.get("/health")
def health():
    # Cheap endpoint for Render health checks and uptime pingers.
    return jsonify(status="ok")
