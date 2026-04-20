# ─── app/services/alert_service.py ───────────────────────────────────────────
"""
Checks an incoming AQI reading and raises/resolves alerts.
Called after every sensor ingest.
"""
from datetime import datetime, timedelta
from flask import current_app
from app import db
from app.models import Alert, AlertSeverity, Citizen


def check_and_create_alerts(zone, aqi_value: float, socketio=None):
    watch = current_app.config["AQI_WATCH_THRESHOLD"]
    warning = current_app.config["AQI_WARNING_THRESHOLD"]
    emergency = current_app.config["AQI_EMERGENCY_THRESHOLD"]

    severity = None
    if aqi_value >= emergency:
        severity = AlertSeverity.EMERGENCY
    elif aqi_value >= warning:
        severity = AlertSeverity.WARNING
    elif aqi_value >= watch:
        severity = AlertSeverity.WATCH

    # Resolve active alerts if AQI is back to good
    if severity is None:
        Alert.query.filter_by(zone_id=zone.zone_id, is_active=True).update(
            {"is_active": False, "resolved_at": datetime.utcnow()}
        )
        db.session.commit()
        return

    # Avoid duplicate alerts within 30 minutes
    recent_alert = Alert.query.filter(
        Alert.zone_id == zone.zone_id,
        Alert.severity == severity,
        Alert.is_active == True,
        Alert.created_at >= datetime.utcnow() - timedelta(minutes=30),
    ).first()

    if recent_alert:
        return

    messages = {
        AlertSeverity.WATCH: f"Air quality in {zone.name} is unhealthy for sensitive groups (AQI {aqi_value:.0f}). Limit prolonged outdoor exertion.",
        AlertSeverity.WARNING: f"Unhealthy air quality detected in {zone.name} (AQI {aqi_value:.0f}). Everyone should reduce outdoor activities.",
        AlertSeverity.EMERGENCY: f"EMERGENCY: Hazardous air quality in {zone.name} (AQI {aqi_value:.0f}). Stay indoors. Close windows and doors.",
    }

    alert = Alert(
        zone_id=zone.zone_id,
        severity=severity,
        aqi_value=aqi_value,
        message=messages[severity],
    )
    db.session.add(alert)
    db.session.commit()

    if socketio:
        socketio.emit(
            "new_alert",
            alert.to_dict(),
            broadcast=True,
        )
