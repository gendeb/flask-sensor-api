from flask import Flask, jsonify

from .config import Config
from .extensions import cache, cors, db


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    cache.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": "*"}})

    from .blueprints.devices import bp as devices_bp
    from .blueprints.health import bp as health_bp
    from .blueprints.readings import bp as readings_bp
    from .blueprints.stats import bp as stats_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(devices_bp, url_prefix="/api/v1/devices")
    app.register_blueprint(readings_bp, url_prefix="/api/v1/readings")
    app.register_blueprint(stats_bp, url_prefix="/api/v1/stats")

    @app.errorhandler(404)
    def not_found(_):
        return jsonify(error="not found"), 404

    @app.errorhandler(500)
    def server_error(_):
        return jsonify(error="internal server error"), 500

    with app.app_context():
        from . import models  # noqa: F401
        from .seed import seed_if_empty

        db.create_all()
        seed_if_empty(app.config["SEED_READINGS"])

    return app
