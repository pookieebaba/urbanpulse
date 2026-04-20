"""
Simple Z-score anomaly detection.
A reading is flagged as anomalous if it deviates more than 3 std-devs
from the zone's mean over the past 7 days.
"""
from datetime import datetime, timedelta
from sqlalchemy import func
from app import db
from app.models import SensorReading


def detect_anomaly(zone_id, aqi_value: float, z_threshold: float = 3.0) -> bool:
    since = datetime.utcnow() - timedelta(days=7)

    stats = db.session.query(
        func.avg(SensorReading.aqi).label("mean"),
        func.stddev_pop(SensorReading.aqi).label("stddev"),
        func.count().label("n"),
    ).filter(
        SensorReading.zone_id == zone_id,
        SensorReading.recorded_at >= since,
    ).first()

    # Need enough data
    if not stats or not stats.n or stats.n < 48:
        return False

    mean = float(stats.mean)
    stddev = float(stats.stddev) if stats.stddev else 0.0

    if stddev < 1.0:  # very stable zone — use a 20% deviation rule instead
        return abs(aqi_value - mean) > mean * 0.20

    z_score = abs(aqi_value - mean) / stddev
    return z_score > z_threshold
