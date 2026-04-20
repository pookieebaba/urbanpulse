import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class BaseConfig:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "jwt-secret-key-change-in-production")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
        "pool_size": 10,
        "max_overflow": 20,
    }

    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # Alert thresholds (AQI levels per EPA standard)
    AQI_WATCH_THRESHOLD = 101       # Unhealthy for Sensitive Groups
    AQI_WARNING_THRESHOLD = 151     # Unhealthy
    AQI_EMERGENCY_THRESHOLD = 201   # Very Unhealthy / Hazardous

    # Sensor simulation
    SENSOR_EMIT_INTERVAL = 30       # seconds
    SENSOR_ZONES = 20

    # Cache TTLs (seconds)
    CACHE_ZONE_LIST_TTL = 60
    CACHE_SENSOR_TTL = 30
    CACHE_FORECAST_TTL = 3600

    # Pagination
    DEFAULT_PAGE_SIZE = 20
    MAX_PAGE_SIZE = 100


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "postgresql://urbanpulse:urbanpulse@localhost:5432/urbanpulse_dev"
    )


class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql://urbanpulse:urbanpulse@localhost:5432/urbanpulse_test"
    )
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=5)


class ProductionConfig(BaseConfig):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    if SQLALCHEMY_DATABASE_URI and SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace(
            "postgres://", "postgresql://", 1
        )


config = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
