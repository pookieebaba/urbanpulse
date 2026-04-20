from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_socketio import SocketIO
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import redis
from config import config

db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
socketio = SocketIO()
limiter = Limiter(key_func=get_remote_address)

redis_client = None


def create_app(config_name="development"):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Extensions
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    limiter.init_app(app)
    socketio.init_app(
        app,
        cors_allowed_origins="*",
        async_mode="threading",
        logger=False,
        engineio_logger=False,
    )

    # Redis
    global redis_client
    redis_client = redis.from_url(
        app.config["REDIS_URL"], decode_responses=True
    )

    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.zones import zones_bp
    from app.routes.sensors import sensors_bp
    from app.routes.alerts import alerts_bp
    from app.routes.reports import reports_bp
    from app.routes.analytics import analytics_bp
    from app.routes.forecast import forecast_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(zones_bp, url_prefix="/api/zones")
    app.register_blueprint(sensors_bp, url_prefix="/api/sensors")
    app.register_blueprint(alerts_bp, url_prefix="/api/alerts")
    app.register_blueprint(reports_bp, url_prefix="/api/reports")
    app.register_blueprint(analytics_bp, url_prefix="/api/analytics")
    app.register_blueprint(forecast_bp, url_prefix="/api/forecast")

    # Register WebSocket events
    from app.services.websocket_service import register_socket_events
    register_socket_events(socketio)

    # Health check
    @app.route("/health")
    def health():
        return {"status": "ok", "service": "UrbanPulse API"}, 200

    return app
