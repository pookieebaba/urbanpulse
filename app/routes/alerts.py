from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from app import db
from app.models import Alert, Citizen
from app.utils.response import success, error
from app.utils.pagination import paginate

alerts_bp = Blueprint("alerts", __name__)


@alerts_bp.route("/active", methods=["GET"])
def active_alerts():
    zone_id = request.args.get("zone_id")
    query = Alert.query.filter_by(is_active=True)
    if zone_id:
        query = query.filter_by(zone_id=zone_id)
    alerts = query.order_by(Alert.created_at.desc()).all()
    return success([a.to_dict() for a in alerts])


@alerts_bp.route("", methods=["GET"])
def all_alerts():
    query = Alert.query.order_by(Alert.created_at.desc())
    result = paginate(query, request)
    result["items"] = [a.to_dict() for a in result.pop("items", [])]
    return success(result)


@alerts_bp.route("/<alert_id>/resolve", methods=["POST"])
@jwt_required()
def resolve_alert(alert_id):
    citizen = Citizen.query.get(get_jwt_identity())
    if not citizen or not citizen.is_admin:
        return error("Admin access required", 403)
    alert = Alert.query.get_or_404(alert_id)
    alert.is_active = False
    alert.resolved_at = datetime.utcnow()
    db.session.commit()
    return success(alert.to_dict(), "Alert resolved")
