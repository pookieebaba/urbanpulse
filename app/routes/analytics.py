from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime, timedelta
from sqlalchemy import func
from app import db
from app.models import SensorReading, Zone, IssueReport, Alert, Citizen
from app.utils.response import success, error

analytics_bp = Blueprint("analytics", __name__)


@analytics_bp.route("/heatmap", methods=["GET"])
def heatmap():
    try:
        start = datetime.fromisoformat(
            request.args.get("start_date", (datetime.utcnow() - timedelta(days=7)).isoformat())
        )
        end = datetime.fromisoformat(
            request.args.get("end_date", datetime.utcnow().isoformat())
        )
    except ValueError:
        return error("Invalid date format, use ISO 8601", 400)

    rows = db.session.query(
        SensorReading.zone_id,
        func.avg(SensorReading.aqi).label("avg_aqi"),
        func.max(SensorReading.aqi).label("max_aqi"),
        func.count().label("samples"),
    ).filter(
        SensorReading.recorded_at.between(start, end)
    ).group_by(SensorReading.zone_id).all()

    zones = {str(z.zone_id): z for z in Zone.query.all()}
    data = []
    for row in rows:
        zid = str(row.zone_id)
        zone = zones.get(zid)
        if zone:
            data.append({
                "zone_id": zid,
                "zone_name": zone.name,
                "latitude": zone.latitude,
                "longitude": zone.longitude,
                "avg_aqi": round(float(row.avg_aqi), 1),
                "max_aqi": round(float(row.max_aqi), 1),
                "aqi_category": SensorReading.aqi_category(float(row.avg_aqi)),
                "samples": int(row.samples),
            })

    data.sort(key=lambda x: x["avg_aqi"], reverse=True)
    return success({"start_date": start.isoformat(), "end_date": end.isoformat(), "zones": data})


@analytics_bp.route("/leaderboard", methods=["GET"])
def leaderboard():
    zone_id = request.args.get("zone_id")
    limit = min(int(request.args.get("limit", 10)), 50)

    query = db.session.query(
        Citizen.citizen_id,
        Citizen.name,
        Citizen.points,
        func.count(IssueReport.report_id).label("report_count"),
    ).join(IssueReport, IssueReport.citizen_id == Citizen.citizen_id, isouter=True)

    if zone_id:
        query = query.filter(IssueReport.zone_id == zone_id)

    rows = (
        query.group_by(Citizen.citizen_id, Citizen.name, Citizen.points)
        .order_by(Citizen.points.desc())
        .limit(limit)
        .all()
    )

    return success([
        {
            "rank": i + 1,
            "citizen_id": str(r.citizen_id),
            "name": r.name,
            "points": r.points,
            "report_count": int(r.report_count or 0),
        }
        for i, r in enumerate(rows)
    ])


@analytics_bp.route("/zone-comparison", methods=["GET"])
def zone_comparison():
    since = datetime.utcnow() - timedelta(hours=24)
    rows = db.session.query(
        SensorReading.zone_id,
        func.avg(SensorReading.aqi).label("avg_aqi"),
        func.avg(SensorReading.pm25).label("avg_pm25"),
        func.avg(SensorReading.noise_db).label("avg_noise"),
        func.avg(SensorReading.co2_ppm).label("avg_co2"),
    ).filter(
        SensorReading.recorded_at >= since
    ).group_by(SensorReading.zone_id).all()

    zones = {str(z.zone_id): z for z in Zone.query.all()}
    result = []
    for row in rows:
        zone = zones.get(str(row.zone_id))
        if zone:
            result.append({
                "zone_id": str(row.zone_id),
                "zone_name": zone.name,
                "avg_aqi": round(float(row.avg_aqi), 1) if row.avg_aqi else None,
                "avg_pm25": round(float(row.avg_pm25), 2) if row.avg_pm25 else None,
                "avg_noise_db": round(float(row.avg_noise), 1) if row.avg_noise else None,
                "avg_co2_ppm": round(float(row.avg_co2), 1) if row.avg_co2 else None,
                "aqi_category": SensorReading.aqi_category(
                    float(row.avg_aqi) if row.avg_aqi else None
                ),
            })

    result.sort(key=lambda x: (x["avg_aqi"] or 0), reverse=True)
    return success(result)


@analytics_bp.route("/city-summary", methods=["GET"])
def city_summary():
    since = datetime.utcnow() - timedelta(hours=24)
    total_zones = Zone.query.count()
    active_alerts = Alert.query.filter_by(is_active=True).count()
    open_reports = IssueReport.query.filter_by(status="pending").count()
    total_citizens = Citizen.query.filter_by(is_active=True).count()

    city_avg = db.session.query(
        func.avg(SensorReading.aqi)
    ).filter(SensorReading.recorded_at >= since).scalar()

    worst_zone_row = db.session.query(
        SensorReading.zone_id,
        func.avg(SensorReading.aqi).label("avg_aqi"),
    ).filter(
        SensorReading.recorded_at >= since
    ).group_by(SensorReading.zone_id).order_by(func.avg(SensorReading.aqi).desc()).first()

    worst_zone = None
    if worst_zone_row:
        zone = Zone.query.get(worst_zone_row.zone_id)
        if zone:
            worst_zone = {"name": zone.name, "avg_aqi": round(float(worst_zone_row.avg_aqi), 1)}

    return success({
        "total_zones": total_zones,
        "active_alerts": active_alerts,
        "open_reports": open_reports,
        "total_citizens": total_citizens,
        "city_avg_aqi_24h": round(float(city_avg), 1) if city_avg else None,
        "city_aqi_category": SensorReading.aqi_category(float(city_avg) if city_avg else None),
        "worst_zone_24h": worst_zone,
    })
