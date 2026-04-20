from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db, redis_client
from app.models import Zone, SensorReading, Citizen
from app.utils.response import success, error
from app.utils.pagination import paginate
import json

zones_bp = Blueprint("zones", __name__)

CACHE_KEY_ZONES = "zones:all"


@zones_bp.route("", methods=["GET"])
def list_zones():
    """List all zones with their current AQI. Cached for 60s."""
    cached = redis_client.get(CACHE_KEY_ZONES)
    if cached:
        return jsonify({"success": True, "data": json.loads(cached)})

    zones = Zone.query.order_by(Zone.name).all()
    data = [z.to_dict(include_aqi=True) for z in zones]

    redis_client.setex(CACHE_KEY_ZONES, 60, json.dumps(data))
    return success(data)


@zones_bp.route("/<zone_id>", methods=["GET"])
def get_zone(zone_id):
    """Get a single zone with full stats."""
    zone = Zone.query.get_or_404(zone_id)

    data = zone.to_dict(include_aqi=True)
    data["active_alerts"] = zone.alerts.filter_by(is_active=True).count()
    data["open_reports"] = zone.reports.filter_by(status="pending").count()

    latest = (
        zone.sensor_readings.order_by(SensorReading.recorded_at.desc()).first()
    )
    data["latest_reading"] = latest.to_dict() if latest else None
    data["aqi_category"] = SensorReading.aqi_category(data.get("current_aqi"))

    return success(data)


@zones_bp.route("/<zone_id>/sensors", methods=["GET"])
def zone_sensor_history(zone_id):
    """
    Paginated sensor readings for a zone.
    Query params: hours (default 24), page, per_page
    """
    zone = Zone.query.get_or_404(zone_id)

    hours = min(int(request.args.get("hours", 24)), 168)  # max 1 week
    from datetime import datetime, timedelta

    since = datetime.utcnow() - timedelta(hours=hours)

    query = (
        SensorReading.query
        .filter(
            SensorReading.zone_id == zone_id,
            SensorReading.recorded_at >= since,
        )
        .order_by(SensorReading.recorded_at.desc())
    )

    result = paginate(query, request)
    result["zone_id"] = zone_id
    result["zone_name"] = zone.name
    result["hours"] = hours
    return success(result)


@zones_bp.route("/<zone_id>/summary", methods=["GET"])
def zone_summary(zone_id):
    """Aggregated stats for a zone over the last 24 hours."""
    from datetime import datetime, timedelta
    from sqlalchemy import func

    zone = Zone.query.get_or_404(zone_id)
    since = datetime.utcnow() - timedelta(hours=24)

    stats = db.session.query(
        func.avg(SensorReading.aqi).label("avg_aqi"),
        func.max(SensorReading.aqi).label("max_aqi"),
        func.min(SensorReading.aqi).label("min_aqi"),
        func.avg(SensorReading.pm25).label("avg_pm25"),
        func.avg(SensorReading.co2_ppm).label("avg_co2"),
        func.avg(SensorReading.temp_c).label("avg_temp"),
        func.avg(SensorReading.noise_db).label("avg_noise"),
        func.count(SensorReading.reading_id).label("reading_count"),
        func.sum(
            db.cast(SensorReading.is_anomaly, db.Integer)
        ).label("anomaly_count"),
    ).filter(
        SensorReading.zone_id == zone_id,
        SensorReading.recorded_at >= since,
    ).first()

    def r(v, decimals=1):
        return round(float(v), decimals) if v is not None else None

    return success({
        "zone_id": zone_id,
        "zone_name": zone.name,
        "period_hours": 24,
        "avg_aqi": r(stats.avg_aqi),
        "max_aqi": r(stats.max_aqi),
        "min_aqi": r(stats.min_aqi),
        "aqi_category": SensorReading.aqi_category(r(stats.avg_aqi)),
        "avg_pm25": r(stats.avg_pm25, 2),
        "avg_co2": r(stats.avg_co2),
        "avg_temp_c": r(stats.avg_temp),
        "avg_noise_db": r(stats.avg_noise),
        "reading_count": int(stats.reading_count or 0),
        "anomaly_count": int(stats.anomaly_count or 0),
    })


# Admin-only routes
@zones_bp.route("", methods=["POST"])
@jwt_required()
def create_zone():
    citizen = Citizen.query.get(get_jwt_identity())
    if not citizen or not citizen.is_admin:
        return error("Admin access required", 403)

    data = request.get_json() or {}
    required = ["name", "code", "latitude", "longitude"]
    for field in required:
        if field not in data:
            return error(f"Field '{field}' is required", 400)

    if Zone.query.filter_by(code=data["code"]).first():
        return error("Zone code already exists", 409)

    zone = Zone(
        name=data["name"],
        code=data["code"].upper(),
        latitude=float(data["latitude"]),
        longitude=float(data["longitude"]),
        area_km2=data.get("area_km2"),
        population=data.get("population"),
        description=data.get("description"),
    )
    db.session.add(zone)
    db.session.commit()
    redis_client.delete(CACHE_KEY_ZONES)

    return success(zone.to_dict(), "Zone created", 201)


@zones_bp.route("/<zone_id>", methods=["PATCH"])
@jwt_required()
def update_zone(zone_id):
    citizen = Citizen.query.get(get_jwt_identity())
    if not citizen or not citizen.is_admin:
        return error("Admin access required", 403)

    zone = Zone.query.get_or_404(zone_id)
    data = request.get_json() or {}

    for field in ["name", "description", "population", "area_km2", "risk_level"]:
        if field in data:
            setattr(zone, field, data[field])

    db.session.commit()
    redis_client.delete(CACHE_KEY_ZONES)
    return success(zone.to_dict(), "Zone updated")
