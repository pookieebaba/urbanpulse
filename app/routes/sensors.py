from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime, timedelta
from sqlalchemy import func
from app import db, redis_client, socketio
from app.models import SensorReading, Zone, Citizen, Alert, AlertSeverity
from app.utils.response import success, error
from app.services.alert_service import check_and_create_alerts
from app.services.anomaly_service import detect_anomaly
import json

sensors_bp = Blueprint("sensors", __name__)


@sensors_bp.route("/ingest", methods=["POST"])
def ingest_reading():
    """
    Ingest a sensor reading from the IoT simulator.
    In production this would be secured with an API key header.
    """
    api_key = request.headers.get("X-Sensor-Key")
    expected_key = "simulator-key-change-in-prod"   # move to env in production
    if api_key != expected_key:
        return error("Invalid sensor API key", 401)

    data = request.get_json()
    if not data:
        return error("JSON body required", 400)

    zone_id = data.get("zone_id")
    zone = Zone.query.get(zone_id)
    if not zone:
        return error("Zone not found", 404)

    aqi = float(data.get("aqi", 0))

    reading = SensorReading(
        zone_id=zone_id,
        aqi=aqi,
        pm25=data.get("pm25"),
        pm10=data.get("pm10"),
        co2_ppm=data.get("co2_ppm"),
        nox_ppb=data.get("nox_ppb"),
        noise_db=data.get("noise_db"),
        temp_c=data.get("temp_c"),
        humidity_pct=data.get("humidity_pct"),
        wind_speed_ms=data.get("wind_speed_ms"),
    )

    # Run anomaly detection
    reading.is_anomaly = detect_anomaly(zone_id, aqi)

    db.session.add(reading)
    db.session.commit()

    # Cache latest reading per zone
    redis_client.setex(
        f"sensor:latest:{zone_id}",
        120,
        json.dumps(reading.to_dict()),
    )

    # Broadcast to WebSocket subscribers
    socketio.emit(
        "sensor_update",
        {
            "zone_id": str(zone_id),
            "zone_name": zone.name,
            "aqi": round(aqi, 1),
            "aqi_category": SensorReading.aqi_category(aqi),
            "is_anomaly": reading.is_anomaly,
            "recorded_at": reading.recorded_at.isoformat() + "Z",
        },
        room=f"zone_{zone_id}",
    )

    # Check if an alert should be raised
    check_and_create_alerts(zone, aqi, socketio)

    return success({"reading_id": reading.reading_id}, "Reading ingested", 201)


@sensors_bp.route("/bulk-ingest", methods=["POST"])
def bulk_ingest():
    """Ingest multiple readings at once (from simulator batch)."""
    api_key = request.headers.get("X-Sensor-Key")
    if api_key != "simulator-key-change-in-prod":
        return error("Invalid sensor API key", 401)

    readings_data = request.get_json()
    if not isinstance(readings_data, list):
        return error("Expected a JSON array", 400)

    inserted = 0
    errors = []

    for item in readings_data[:50]:  # cap at 50 per request
        zone = Zone.query.get(item.get("zone_id"))
        if not zone:
            errors.append(f"Zone {item.get('zone_id')} not found")
            continue

        aqi = float(item.get("aqi", 0))
        reading = SensorReading(
            zone_id=zone.zone_id,
            aqi=aqi,
            pm25=item.get("pm25"),
            pm10=item.get("pm10"),
            co2_ppm=item.get("co2_ppm"),
            nox_ppb=item.get("nox_ppb"),
            noise_db=item.get("noise_db"),
            temp_c=item.get("temp_c"),
            humidity_pct=item.get("humidity_pct"),
            wind_speed_ms=item.get("wind_speed_ms"),
            is_anomaly=detect_anomaly(zone.zone_id, aqi),
        )
        db.session.add(reading)
        inserted += 1

    db.session.commit()
    return success({"inserted": inserted, "errors": errors}, f"{inserted} readings ingested")


@sensors_bp.route("/latest", methods=["GET"])
def latest_all_zones():
    """Latest reading for every zone (for the dashboard overview)."""
    zones = Zone.query.all()
    result = []

    for zone in zones:
        cache_key = f"sensor:latest:{zone.zone_id}"
        cached = redis_client.get(cache_key)

        if cached:
            reading_dict = json.loads(cached)
        else:
            latest = (
                zone.sensor_readings
                .order_by(SensorReading.recorded_at.desc())
                .first()
            )
            reading_dict = latest.to_dict() if latest else None
            if reading_dict:
                redis_client.setex(cache_key, 60, json.dumps(reading_dict))

        result.append({
            "zone_id": str(zone.zone_id),
            "zone_name": zone.name,
            "zone_code": zone.code,
            "latitude": zone.latitude,
            "longitude": zone.longitude,
            "reading": reading_dict,
            "aqi_category": SensorReading.aqi_category(
                reading_dict["aqi"] if reading_dict else None
            ),
        })

    return success(result)


@sensors_bp.route("/timeseries/<zone_id>", methods=["GET"])
def timeseries(zone_id):
    """
    Hourly-averaged AQI time series for charting.
    Query params: hours (default 48)
    """
    zone = Zone.query.get_or_404(zone_id)
    hours = min(int(request.args.get("hours", 48)), 720)
    since = datetime.utcnow() - timedelta(hours=hours)

    rows = db.session.query(
        func.date_trunc("hour", SensorReading.recorded_at).label("hour"),
        func.avg(SensorReading.aqi).label("avg_aqi"),
        func.avg(SensorReading.pm25).label("avg_pm25"),
        func.avg(SensorReading.co2_ppm).label("avg_co2"),
        func.avg(SensorReading.temp_c).label("avg_temp"),
        func.count().label("n"),
    ).filter(
        SensorReading.zone_id == zone_id,
        SensorReading.recorded_at >= since,
    ).group_by("hour").order_by("hour").all()

    series = [
        {
            "timestamp": row.hour.isoformat() + "Z",
            "aqi": round(float(row.avg_aqi), 1) if row.avg_aqi else None,
            "pm25": round(float(row.avg_pm25), 2) if row.avg_pm25 else None,
            "co2_ppm": round(float(row.avg_co2), 1) if row.avg_co2 else None,
            "temp_c": round(float(row.avg_temp), 1) if row.avg_temp else None,
            "sample_count": int(row.n),
        }
        for row in rows
    ]

    return success({
        "zone_id": zone_id,
        "zone_name": zone.name,
        "hours": hours,
        "series": series,
    })


@sensors_bp.route("/anomalies", methods=["GET"])
def recent_anomalies():
    """List recent anomalous readings across all zones."""
    hours = min(int(request.args.get("hours", 24)), 168)
    since = datetime.utcnow() - timedelta(hours=hours)

    readings = (
        SensorReading.query
        .filter(
            SensorReading.is_anomaly == True,
            SensorReading.recorded_at >= since,
        )
        .order_by(SensorReading.recorded_at.desc())
        .limit(100)
        .all()
    )

    return success([r.to_dict() for r in readings])
